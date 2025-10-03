#!/usr/bin/env python3
"""
hashmap_cli.py

A production-grade, single-file toolkit:
- TwoLevelChainingMap (2-level chaining, cache-friendly)
- RobinHoodMap (open addressing with Robin Hood displacement; tombstone-aware)
- HybridAdaptiveHashMap (adaptive: monitors health, migrates incrementally)
- Profiler, synthetic workload generator (Zipf + adversarial), CSV runner
- Prometheus-style /metrics + zero-dependency dashboard
- Snapshots (pickle) with optional gzip compression (.gz or --compress)
- Proactive compaction tick (--compact-interval)
- Offline snapshot compaction for Robin Hood
- Snapshot verification (invariants) + --repair (safe compaction)
- CI JSON summary with throughput and percentile latencies (reservoir sampling)

New in this version:
  * Snapshot serialization hardened:
      - Callbacks (on_migration/on_compaction) are **not pickled**. Config is saved as a plain dict.
  * run-csv:
      --json-summary-out FILE
      --latency-sample-k K (default 1000)
      --latency-sample-every N (default 128)
      -> adds p50/p90/p99 latency (ms) for overall **and per op**: put/get/del
  * Observability:
      - Added hashmap_compactions_total counter (metrics + JSON)
  * Reliability:
      - Metrics server shuts down via try/finally even on errors.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import logging
import math
import os
import pickle
import random
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, Iterator, List, Optional, Tuple, cast
from urllib.parse import parse_qs, urlparse
from contextlib import redirect_stdout

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

try:  # pragma: no cover - executed only during development
    from adhash.config import AppConfig, WatchdogPolicy, load_app_config
    from adhash.contracts.error import (
        Exit,
        BadInputError,
        InvariantError,
        IOErrorEnvelope,
        PolicyError,
        guard_cli,
    )
    from adhash.io.snapshot_header import read_snapshot as read_versioned_snapshot
    from adhash.io.snapshot_header import write_snapshot as write_versioned_snapshot
except ModuleNotFoundError:  # pragma: no cover - fallback when running from repo root
    if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    from adhash.config import AppConfig, WatchdogPolicy, load_app_config
    from adhash.contracts.error import (
        Exit,
        BadInputError,
        InvariantError,
        IOErrorEnvelope,
        PolicyError,
        guard_cli,
    )
    from adhash.io.snapshot_header import read_snapshot as read_versioned_snapshot
    from adhash.io.snapshot_header import write_snapshot as write_versioned_snapshot

# --------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------
logger = logging.getLogger("hashmap_cli")
logger.setLevel(logging.INFO)
logger.propagate = False

DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S"
DEFAULT_LOG_MAX_BYTES = 5_000_000
DEFAULT_LOG_BACKUP_COUNT = 5
DEFAULT_CSV_MAX_ROWS = 5_000_000
DEFAULT_CSV_MAX_BYTES = 500 * 1024 * 1024
_SUMMARY_QUANTILES = {"p50": "0.5", "p90": "0.9", "p99": "0.99"}


def _format_bucket_label(bound: float) -> str:
    return "+Inf" if math.isinf(bound) else f"{bound:.6f}"


class JsonFormatter(logging.Formatter):
    """Render log records as JSON objects."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload = {
            "ts": self.formatTime(record, DEFAULT_LOG_DATEFMT),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    use_json: bool = False,
    log_file: Optional[str] = None,
    *,
    max_bytes: int = DEFAULT_LOG_MAX_BYTES,
    backup_count: int = DEFAULT_LOG_BACKUP_COUNT,
) -> None:
    """Configure console (and optional rotating file) logging."""

    formatter: logging.Formatter
    if use_json:
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_LOG_DATEFMT)

    logger.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file:
        handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        handler.setFormatter(formatter if use_json else JsonFormatter())
        logger.addHandler(handler)


configure_logging()

APP_CONFIG: AppConfig = AppConfig()
OUTPUT_JSON: bool = False


def set_app_config(cfg: AppConfig) -> None:
    global APP_CONFIG
    APP_CONFIG = cfg


def emit_success(command: str, *, text: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    if OUTPUT_JSON:
        payload: Dict[str, Any] = {"ok": True, "command": command}
        if data:
            payload.update(data)
        if text is not None and "result" not in payload:
            payload["result"] = text
        print(json.dumps(payload, ensure_ascii=False))
    else:
        if text is not None:
            print(text)

# --------------------------------------------------------------------
# Compressed pickle I/O helpers
# --------------------------------------------------------------------
def _open_for_read(path: str):
    """Open a snapshot for reading (auto-detect .gz)."""
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")

def _open_for_write(path: str, compress: bool):
    """Open a snapshot for writing; gzip if --compress or .gz suffix."""
    use_gz = compress or path.endswith(".gz")
    return gzip.open(path, "wb") if use_gz else open(path, "wb")


def _load_snapshot_any(path: str) -> Any:
    """Load snapshot using the versioned header format, falling back to legacy pickles."""

    p = Path(path)
    try:
        return read_versioned_snapshot(p)
    except Exception as exc:
        logger.debug("Falling back to legacy snapshot load for %s: %s", path, exc)
        with _open_for_read(path) as fh:
            return pickle.load(fh)


def _save_snapshot_any(obj: Any, path: str, compress: bool) -> None:
    """Persist snapshot via versioned header; fall back to legacy pickle on failure."""

    p = Path(path)
    try:
        write_versioned_snapshot(p, obj, compress=compress or path.endswith(".gz"))
    except Exception as exc:
        logger.debug("Falling back to legacy snapshot save for %s: %s", path, exc)
        with _open_for_write(path, compress) as fh:
            pickle.dump(obj, fh)

# --------------------------------------------------------------------
# Shared constants
# --------------------------------------------------------------------
_HASH_GOLDEN_64: int = 0x9E3779B97F4A7C15  # golden-ratio mixer for second hash

# --------------------------------------------------------------------
# Two-level chaining backend
# --------------------------------------------------------------------
@dataclass
class _Entry:
    key: Any
    value: Any

class TwoLevelChainingMap:
    """
    Hash map with 2-level chaining: M buckets, each with G small vectors.
    Insert: append; Delete: swap-pop; Rehash when LF>0.8
    """
    __slots__ = ("M", "G", "_buckets", "_size")

    def __init__(self, initial_buckets: int = 64, groups_per_bucket: int = 8) -> None:
        if initial_buckets < 1 or (initial_buckets & (initial_buckets - 1)) != 0:
            raise ValueError("initial_buckets must be a power of two")
        if groups_per_bucket < 1 or (groups_per_bucket & (groups_per_bucket - 1)) != 0:
            raise ValueError("groups_per_bucket must be a power of two")
        self.M = initial_buckets
        self.G = groups_per_bucket
        self._buckets: List[List[List[_Entry]]] = [[[] for _ in range(self.G)] for _ in range(self.M)]
        self._size = 0

    def __len__(self) -> int: return self._size

    def _h1(self, key: Any) -> int: return hash(key)

    def _h2(self, key: Any) -> int:
        x = hash((key, _HASH_GOLDEN_64))
        return x ^ (x >> 16)

    def _index_group(self, key: Any) -> Tuple[int, int]:
        i = self._h1(key) & (self.M - 1)
        g = self._h2(key) & (self.G - 1)
        return i, g

    def load_factor(self) -> float:
        return self._size / self.M if self.M else 0.0

    def _rehash(self, new_M: int) -> None:
        old = self._buckets
        self.M = new_M
        self._buckets = [[[] for _ in range(self.G)] for _ in range(self.M)]
        for groups in old:
            for grp in groups:
                for e in grp:
                    i, g = self._index_group(e.key)
                    self._buckets[i][g].append(e)

    def put(self, key: Any, value: Any) -> None:
        i, g = self._index_group(key)
        grp = self._buckets[i][g]
        for e in grp:
            if e.key == key:
                e.value = value
                return
        grp.append(_Entry(key, value))
        self._size += 1
        if self.load_factor() > 0.8:
            self._rehash(self.M * 2)

    def get(self, key: Any) -> Optional[Any]:
        i, g = self._index_group(key)
        for e in self._buckets[i][g]:
            if e.key == key:
                return e.value
        return None

    def delete(self, key: Any) -> bool:
        i, g = self._index_group(key)
        grp = self._buckets[i][g]
        for idx, e in enumerate(grp):
            if e.key == key:
                grp[idx] = grp[-1]
                grp.pop()
                self._size -= 1
                return True
        return False

    def items(self) -> Iterator[Tuple[Any, Any]]:
        for groups in self._buckets:
            for grp in groups:
                for e in grp:
                    yield e.key, e.value

    def max_group_len(self) -> int:
        mg = 0
        for groups in self._buckets:
            for grp in groups:
                if len(grp) > mg:
                    mg = len(grp)
        return mg

    # Snapshot
    def save(self, filepath: str, compress: bool = False) -> None:
        with _open_for_write(filepath, compress) as f:
            pickle.dump(self, f)

    @staticmethod
    def load(filepath: str) -> "TwoLevelChainingMap":
        with _open_for_read(filepath) as f:
            obj = pickle.load(f)
        if not isinstance(obj, TwoLevelChainingMap):
            raise TypeError("Snapshot is not a TwoLevelChainingMap")
        return obj

# --------------------------------------------------------------------
# Robin Hood backend
# --------------------------------------------------------------------
class _Tombstone:
    __slots__ = ()
_TOMBSTONE = _Tombstone()

@dataclass
class _RHEntry:
    key: Any
    value: Any

class RobinHoodMap:
    """
    Robin Hood linear probing with tombstones and compaction.
    Ensures bounded scans by checking up to _cap slots on get/delete.
    """
    __slots__ = ("_table", "_size", "_cap", "_mask", "_tombstones")

    def __init__(self, initial_capacity: int = 64) -> None:
        if initial_capacity < 1 or (initial_capacity & (initial_capacity - 1)) != 0:
            raise ValueError("initial_capacity must be a power of two")
        self._cap = initial_capacity
        self._mask = initial_capacity - 1
        self._table: List[Optional[Any]] = [None] * initial_capacity
        self._size = 0
        self._tombstones = 0

    def __len__(self) -> int: return self._size
    def load_factor(self) -> float: return self._size / self._cap if self._cap else 0.0
    def tombstone_ratio(self) -> float: return (self._tombstones / self._cap) if self._cap else 0.0

    def _idx(self, h: int) -> int: return h & self._mask

    def _probe_distance(self, ideal_idx: int, cur_idx: int) -> int:
        return cur_idx - ideal_idx if cur_idx >= ideal_idx else (cur_idx + self._cap) - ideal_idx

    def _resize(self, new_cap: int) -> None:
        old = self._table
        self._cap = new_cap
        self._mask = new_cap - 1
        self._table = [None] * new_cap
        self._size = 0
        self._tombstones = 0
        for slot in old:
            if isinstance(slot, _RHEntry):
                self.put(slot.key, slot.value)

    def compact(self) -> None:
        """Purge tombstones and rebuild at same capacity."""
        self._resize(self._cap)

    def put(self, key: Any, value: Any) -> None:
        if self.load_factor() > 0.85:
            self._resize(self._cap * 2)
        h = hash(key)
        idx = self._idx(h)
        cur = _RHEntry(key, value)
        dist = 0
        while True:
            slot = self._table[idx]
            if slot is None:
                self._table[idx] = cur
                self._size += 1
                return
            if slot is _TOMBSTONE:
                self._table[idx] = cur
                self._size += 1
                self._tombstones -= 1
                return
            if slot.key == key:
                slot.value = value
                return
            ideal = self._idx(hash(slot.key))
            slot_dist = self._probe_distance(ideal, idx)
            if slot_dist < dist:
                self._table[idx], cur = cur, slot
                dist = slot_dist
            idx = (idx + 1) & self._mask
            dist += 1

    def get(self, key: Any) -> Optional[Any]:
        h = hash(key)
        idx = self._idx(h)
        scanned = 0
        while scanned <= self._cap:
            slot = self._table[idx]
            if slot is None:
                return None
            if isinstance(slot, _RHEntry) and slot.key == key:
                return slot.value
            idx = (idx + 1) & self._mask
            scanned += 1
        return None

    def delete(self, key: Any) -> bool:
        h = hash(key)
        idx = self._idx(h)
        scanned = 0
        while scanned <= self._cap:
            slot = self._table[idx]
            if slot is None:
                return False
            if isinstance(slot, _RHEntry) and slot.key == key:
                self._table[idx] = _TOMBSTONE
                self._size -= 1
                self._tombstones += 1
                return True
            idx = (idx + 1) & self._mask
            scanned += 1
        return False

    def items(self) -> Iterator[Tuple[Any, Any]]:
        for slot in self._table:
            if isinstance(slot, _RHEntry):
                yield slot.key, slot.value

    def avg_probe_estimate(self, step: int = 8) -> float:
        if self._size == 0:
            return 0.0
        total = 0
        cnt = 0
        for i in range(0, self._cap, step):
            slot = self._table[i]
            if isinstance(slot, _RHEntry):
                ideal = self._idx(hash(slot.key))
                total += self._probe_distance(ideal, i)
                cnt += 1
        return total / max(cnt, 1)

    # Snapshot
    def save(self, filepath: str, compress: bool = False) -> None:
        with _open_for_write(filepath, compress) as f:
            pickle.dump(self, f)

    @staticmethod
    def load(filepath: str) -> "RobinHoodMap":
        with _open_for_read(filepath) as f:
            obj = pickle.load(f)
        if not isinstance(obj, RobinHoodMap):
            raise TypeError("Snapshot is not a RobinHoodMap")
        return obj

# --------------------------------------------------------------------
# Metrics + dashboard
# --------------------------------------------------------------------
class Metrics:
    def __init__(self) -> None:
        self.ops_total = 0
        self.puts_total = 0
        self.gets_total = 0
        self.dels_total = 0
        self.migrations_total = 0
        self.compactions_total = 0  # NEW
        self.load_factor = 0.0
        self.max_group_len = 0.0
        self.avg_probe_estimate = 0.0
        self.backend_name = "unknown"
        self.latest_tick: Optional[Dict[str, Any]] = None
        self.tombstone_ratio = 0.0
        self.alert_flags: Dict[str, bool] = {}
        self.active_alerts: List[Dict[str, Any]] = []
        self.latency_summary_stats: Dict[str, Dict[str, float]] = {}
        self.latency_histograms: Dict[str, List[Tuple[float, int]]] = {}
        self.history_buffer: Optional[Deque[Dict[str, Any]]] = None
        self.events_history: Deque[Dict[str, Any]] = deque(maxlen=512)
        self.key_heatmap: Dict[str, Any] = {
            "rows": 0,
            "cols": 0,
            "matrix": [],
            "max": 0,
            "total": 0,
            "slot_span": 1,
            "original_slots": 0,
        }

    def render(self) -> str:
        lines = [
            "# HELP hashmap_ops_total Total operations processed",
            "# TYPE hashmap_ops_total counter",
            f"hashmap_ops_total {self.ops_total}",
            "# HELP hashmap_puts_total Total put operations",
            "# TYPE hashmap_puts_total counter",
            f"hashmap_puts_total {self.puts_total}",
            "# HELP hashmap_gets_total Total get operations",
            "# TYPE hashmap_gets_total counter",
            f"hashmap_gets_total {self.gets_total}",
            "# HELP hashmap_dels_total Total delete operations",
            "# TYPE hashmap_dels_total counter",
            f"hashmap_dels_total {self.dels_total}",
            "# HELP hashmap_migrations_total Backend migrations",
            "# TYPE hashmap_migrations_total counter",
            f"hashmap_migrations_total {self.migrations_total}",
            "# HELP hashmap_compactions_total Backend compactions",
            "# TYPE hashmap_compactions_total counter",
            f"hashmap_compactions_total {self.compactions_total}",
            "# HELP hashmap_load_factor Current load factor",
            "# TYPE hashmap_load_factor gauge",
            f"hashmap_load_factor {self.load_factor:.6f}",
            "# HELP hashmap_max_group_len Max inner group length (chaining)",
            "# TYPE hashmap_max_group_len gauge",
            f"hashmap_max_group_len {self.max_group_len:.6f}",
            "# HELP hashmap_avg_probe_estimate Estimated avg probe distance (robinhood)",
            "# TYPE hashmap_avg_probe_estimate gauge",
            f"hashmap_avg_probe_estimate {self.avg_probe_estimate:.6f}",
            "# HELP hashmap_tombstone_ratio Tombstone ratio for RobinHood backend",
            "# TYPE hashmap_tombstone_ratio gauge",
            f"hashmap_tombstone_ratio {self.tombstone_ratio:.6f}",
            "# HELP hashmap_backend_info Backend in use (label)",
            "# TYPE hashmap_backend_info gauge",
            f'hashmap_backend_info{{name="{self.backend_name}"}} 1',
        ]

        latest = self.latest_tick or {}
        latency_ms = latest.get("latency_ms", {})
        if latency_ms:
            lines.append("# HELP hashmap_latency_ms Latency percentiles (ms) by operation and quantile")
            lines.append("# TYPE hashmap_latency_ms gauge")
            for op, packet in latency_ms.items():
                for q, value in packet.items():
                    lines.append(f'hashmap_latency_ms{{op="{op}",quantile="{q}"}} {value:.6f}')

            summary_ops = {
                op: stats for op, stats in self.latency_summary_stats.items()
                if stats.get("count", 0)
            }
            if summary_ops:
                lines.append("# HELP hashmap_latency_ms_summary Sampled latency summaries (ms) per operation")
                lines.append("# TYPE hashmap_latency_ms_summary summary")
                for op in sorted(summary_ops):
                    packet = latency_ms.get(op, {})
                    stats = summary_ops[op]
                    for quantile_key, value in packet.items():
                        quantile_label = _SUMMARY_QUANTILES.get(quantile_key)
                        if quantile_label is None:
                            continue
                        lines.append(
                            f'hashmap_latency_ms_summary{{op="{op}",quantile="{quantile_label}"}} {value:.6f}'
                        )
                    lines.append(
                        f'hashmap_latency_ms_summary_sum{{op="{op}"}} {stats.get("sum", 0.0):.6f}'
                    )
                    lines.append(
                        f'hashmap_latency_ms_summary_count{{op="{op}"}} {int(stats.get("count", 0))}'
                    )

            hist_ops = {
                op: buckets for op, buckets in self.latency_histograms.items() if buckets
            }
            if hist_ops:
                lines.append("# HELP hashmap_latency_ms_hist Sampled latency histogram (ms) per operation")
                lines.append("# TYPE hashmap_latency_ms_hist histogram")
                for op in sorted(hist_ops):
                    buckets = hist_ops[op]
                    stats = self.latency_summary_stats.get(op, {})
                    for upper, cumulative in buckets:
                        label = _format_bucket_label(upper)
                        lines.append(
                            f'hashmap_latency_ms_hist_bucket{{op="{op}",le="{label}"}} {cumulative}'
                        )
                    lines.append(
                        f'hashmap_latency_ms_hist_sum{{op="{op}"}} {stats.get("sum", 0.0):.6f}'
                    )
                    lines.append(
                        f'hashmap_latency_ms_hist_count{{op="{op}"}} {int(stats.get("count", 0))}'
                    )

        probe_hist = latest.get("probe_hist")
        if isinstance(probe_hist, list) and probe_hist:
            lines.append("# HELP hashmap_probe_length_count Probe length histogram (count per distance)")
            lines.append("# TYPE hashmap_probe_length_count gauge")
            for distance, count in probe_hist:
                lines.append(f'hashmap_probe_length_count{{distance="{distance}"}} {count}')

        if self.alert_flags:
            lines.append("# HELP hashmap_watchdog_alert_active Guardrail alert state (1=active)")
            lines.append("# TYPE hashmap_watchdog_alert_active gauge")
            for metric, active in sorted(self.alert_flags.items()):
                value = 1 if active else 0
                lines.append(f'hashmap_watchdog_alert_active{{metric="{metric}"}} {value}')

        return "\n".join(lines) + "\n"


def apply_tick_to_metrics(metrics: "Metrics", tick: Dict[str, Any]) -> None:
    """Apply a metrics tick dictionary to the in-memory Metrics object."""

    metrics.ops_total = int(tick.get("ops", metrics.ops_total))
    ops_by_type = tick.get("ops_by_type") or {}
    metrics.puts_total = int(ops_by_type.get("put", metrics.puts_total))
    metrics.gets_total = int(ops_by_type.get("get", metrics.gets_total))
    metrics.dels_total = int(ops_by_type.get("del", metrics.dels_total))
    metrics.migrations_total = int(tick.get("migrations", metrics.migrations_total))
    metrics.compactions_total = int(tick.get("compactions", metrics.compactions_total))
    metrics.load_factor = float(tick.get("load_factor", metrics.load_factor))
    metrics.max_group_len = float(tick.get("max_group_len", metrics.max_group_len))
    metrics.avg_probe_estimate = float(tick.get("avg_probe_estimate", metrics.avg_probe_estimate))
    metrics.tombstone_ratio = float(tick.get("tombstone_ratio", metrics.tombstone_ratio))
    metrics.backend_name = str(tick.get("backend", metrics.backend_name))

    raw_alerts = tick.get("alerts")
    alert_items: List[Dict[str, Any]] = []
    if isinstance(raw_alerts, list):
        for item in raw_alerts:
            if isinstance(item, dict):
                alert_items.append(item)
    metrics.active_alerts = alert_items  # type: ignore[assignment]
    metrics.alert_flags = {
        item.get("metric", f"alert-{idx}"): True
        for idx, item in enumerate(alert_items)
    }

    latency_ms = tick.get("latency_ms")
    if isinstance(latency_ms, dict):
        metrics.latency_summary_stats = {
            op: {"count": int(packet.get("count", 0)), "sum": float(packet.get("sum", 0.0))}
            for op, packet in latency_ms.items()
            if isinstance(packet, dict)
        }

    latency_hist = tick.get("latency_hist_ms")
    if isinstance(latency_hist, dict):
        parsed_hist: Dict[str, List[Tuple[float, int]]] = {}
        for label, buckets in latency_hist.items():
            if not isinstance(buckets, list):
                continue
            parsed: List[Tuple[float, int]] = []
            for bucket in buckets:
                if not isinstance(bucket, dict):
                    continue
                value_le = bucket.get("le")
                value_count = bucket.get("count", 0)
                if value_le is None or value_count is None:
                    continue
                try:
                    upper = float(value_le)
                    count = int(value_count)
                except (TypeError, ValueError):
                    continue
                parsed.append((upper, count))
            if parsed:
                parsed_hist[label] = parsed
        metrics.latency_histograms = parsed_hist

    key_heatmap = tick.get("key_heatmap")
    if isinstance(key_heatmap, dict):
        metrics.key_heatmap = key_heatmap

    metrics.latest_tick = tick
    history = getattr(metrics, "history_buffer", None)
    if history is not None:
        history.append(tick)

    events = tick.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                metrics.events_history.append(event)


def _parse_tick_line(line: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        logger.debug("Ignored invalid metrics line: %s", line.strip())
        return None
    if not isinstance(payload, dict):
        return None
    schema = payload.get("schema")
    if schema not in (None, "metrics.v1"):
        logger.debug("Skipping metrics tick with schema=%s", schema)
        return None
    return payload


def _stream_metrics_file(
    path: Path,
    follow: bool,
    callback: Callable[[Dict[str, Any]], None],
    poll_interval: float,
) -> None:
    waiting_logged = False
    while True:
        try:
            with path.open("r", encoding="utf-8") as fh:
                waiting_logged = False
                while True:
                    position = fh.tell()
                    line = fh.readline()
                    if not line:
                        if not follow:
                            return
                        time.sleep(poll_interval)
                        fh.seek(position)
                        continue
                    tick = _parse_tick_line(line)
                    if tick is not None:
                        callback(tick)
                # unreachable
        except FileNotFoundError:
            if not follow:
                logger.error("Metrics source not found: %s", path)
                return
            if not waiting_logged:
                logger.info("Waiting for metrics source to appear: %s", path)
                waiting_logged = True
            time.sleep(poll_interval)
            continue

class ThresholdWatchdog:
    """Evaluate metrics against configured guardrails and emit alerts."""

    def __init__(self, policy: WatchdogPolicy) -> None:
        self.policy = policy
        self._state: Dict[str, bool] = {}

    def evaluate(self, tick: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
        if not self.policy.enabled:
            if any(self._state.values()):
                logger.info("Watchdog disabled; clearing %d active alerts", sum(1 for active in self._state.values() if active))
            self._state.clear()
            return [], {}

        backend = str(tick.get("backend", "unknown"))
        alerts: List[Dict[str, Any]] = []
        flags: Dict[str, bool] = {}

        checks = [
            ("load_factor", tick.get("load_factor"), self.policy.load_factor_warn, "Load factor guardrail exceeded"),
            ("avg_probe_estimate", tick.get("avg_probe_estimate"), self.policy.avg_probe_warn, "Probe length guardrail exceeded"),
            ("tombstone_ratio", tick.get("tombstone_ratio"), self.policy.tombstone_ratio_warn, "Tombstone ratio guardrail exceeded"),
        ]

        for metric, raw_value, threshold, prefix in checks:
            if threshold is None:
                if self._state.pop(metric, False):
                    logger.info("Watchdog cleared (%s): threshold disabled", metric)
                continue

            value = self._safe_float(raw_value)
            active = value is not None and value >= threshold
            was_active = self._state.get(metric, False)

            if active:
                if not was_active:
                    logger.warning(
                        "Watchdog alert (%s): %.3f ≥ %.3f [backend=%s]",
                        metric,
                        value,
                        threshold,
                        backend,
                    )
                alert = {
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "severity": "warning",
                    "backend": backend,
                    "message": f"{prefix}: {value:.3f} ≥ {threshold:.3f}",
                }
                alerts.append(alert)
            else:
                if was_active:
                    value_repr = "n/a" if value is None else f"{value:.3f}"
                    logger.info(
                        "Watchdog resolved (%s): value=%s < %.3f [backend=%s]",
                        metric,
                        value_repr,
                        threshold,
                        backend,
                    )

            self._state[metric] = active
            flags[metric] = active

        return alerts, flags

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(out):
            return None
        return out

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>Adaptive HashMap Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
body{font-family:system-ui,Arial,sans-serif;margin:24px;background:#f8fafc;color:#0f172a}
h1{margin:0 0 8px;font-size:24px}
.summary{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.summary .card{background:#fff;border:1px solid #cbd5f5;border-radius:10px;padding:12px 16px;box-shadow:0 1px 2px rgba(15,23,42,0.08)}
.summary strong{display:block;font-size:12px;color:#475569;text-transform:uppercase;letter-spacing:0.04em}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.chart{background:#fff;border:1px solid #cbd5f5;border-radius:12px;padding:8px;box-shadow:0 1px 3px rgba(15,23,42,0.1)}
.banner{margin:16px 0;padding:14px;border-radius:10px;border:1px solid #f6993f;background:#fff7ed;color:#9a3412;display:none}
.hidden{display:none}
.metrics-note{margin-top:12px;font-size:13px;color:#475569}
</style>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head><body>
<h1>Adaptive HashMap Dashboard</h1>
<p class="metrics-note">Polling <code>/api/metrics</code>, <code>/api/metrics/history</code>, and histogram/heatmap endpoints every 2s</p>
<div class="summary">
  <div class="card"><strong>Backend</strong><span id="backend">-</span></div>
  <div class="card"><strong>Total Ops</strong><span id="ops">0</span></div>
  <div class="card"><strong>Puts</strong><span id="puts">0</span></div>
  <div class="card"><strong>Gets</strong><span id="gets">0</span></div>
  <div class="card"><strong>Dels</strong><span id="dels">0</span></div>
  <div class="card"><strong>Migrations</strong><span id="migs">0</span></div>
</div>
<div id="alert-banner" class="banner hidden"></div>
<div class="charts">
  <div id="chart-load" class="chart"></div>
  <div id="chart-probe" class="chart"></div>
  <div id="chart-tombstone" class="chart"></div>
  <div id="chart-throughput" class="chart"></div>
  <div id="chart-latency" class="chart"></div>
  <div id="chart-probe-bar" class="chart"></div>
  <div id="chart-heatmap" class="chart" style="grid-column: span 2;"></div>
</div>
<div id="events-panel" class="chart" style="margin-top:16px;">
  <h2 style="margin:0 0 8px;font-size:18px;">Recent Events</h2>
  <ul id="events-list" style="list-style:none;padding:0;margin:0;font-size:14px;color:#334155;"></ul>
</div>
<script>
var banner = document.getElementById('alert-banner');
var MAX_POINTS = 120;
var series = {
  load: {x: [], y: []},
  probe: {x: [], y: []},
  tombstone: {x: [], y: []},
  throughput: {x: [], y: []}
};
var transparent = 'rgba(0,0,0,0)';
var chartOpts = {displayModeBar: false};

function safeNumber(value, fallback) {
  var num = Number(value);
  return isFinite(num) ? num : fallback;
}

function initPlot(id, title, yTitle, yRange) {
  Plotly.newPlot(id, [{x: [], y: [], mode: 'lines', line: {shape: 'spline'}}], {
    title: {text: title, font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: 'Seconds'},
    yaxis: yRange ? {title: yTitle, range: yRange} : {title: yTitle},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent
  }, chartOpts);
}

function initLatencyChart() {
  Plotly.newPlot('chart-latency', [{x: [], y: [], type: 'bar', marker: {color: '#2563eb'}}], {
    title: {text: 'Latency Histogram (ms)', font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: '≤ latency (ms)'},
    yaxis: {title: 'Count'},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent
  }, chartOpts);
}

function initProbeBarChart() {
  Plotly.newPlot('chart-probe-bar', [{x: [], y: [], type: 'bar', marker: {color: '#0ea5e9'}}], {
    title: {text: 'Probe Length Distribution', font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: 'Distance'},
    yaxis: {title: 'Count'},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent
  }, chartOpts);
}

function initHeatmapChart() {
  Plotly.newPlot('chart-heatmap', [{z: [[0]], type: 'heatmap', colorscale: 'YlGnBu', hoverongaps: false}], {
    title: {text: 'Key Distribution Heatmap', font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: 'Segment', zeroline: false},
    yaxis: {title: 'Row', autorange: 'reversed', zeroline: false},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent
  }, chartOpts);
}

initPlot('chart-load', 'Load Factor', 'ratio', [0, 1]);
initPlot('chart-probe', 'Avg Probe Distance', 'steps', null);
initPlot('chart-tombstone', 'Tombstone Ratio', 'ratio', [0, 1]);
initPlot('chart-throughput', 'Ops / Second', 'ops/s', null);
initLatencyChart();
initProbeBarChart();
initHeatmapChart();

function pushPoint(key, t, value) {
  if (!isFinite(value)) {
    return;
  }
  var target = series[key];
  if (!target) {
    return;
  }
  if (target.x.length && t < target.x[target.x.length - 1]) {
    target.x = [];
    target.y = [];
    Plotly.update('chart-' + key, {x: [[]], y: [[]]});
  }
  target.x.push(t);
  target.y.push(value);
  if (target.x.length > MAX_POINTS) {
    target.x.shift();
    target.y.shift();
  }
  Plotly.update('chart-' + key, {x: [target.x], y: [target.y]});
}

function updateLatencyHistogram(payload) {
  var operations = payload && typeof payload === 'object' ? payload.operations : null;
  var overall = operations && typeof operations === 'object' && Array.isArray(operations.overall) ? operations.overall : [];
  var x = [];
  var y = [];
  var cumulative = 0;
  for (var i = 0; i < overall.length; i += 1) {
    var bucket = overall[i];
    if (!bucket) {
      continue;
    }
    var bound = bucket.le;
    if (bound === undefined || bound === null) {
      bound = bucket.bound;
    }
    var label;
    if (bound === undefined || bound === null || bound === '+Inf' || bound === Infinity) {
      label = '∞';
    } else {
      label = String(bound);
    }
    var rawCount = safeNumber(bucket.count, 0);
    if (rawCount < 0) {
      continue;
    }
    var count = rawCount - cumulative;
    cumulative = rawCount;
    x.push(label);
    y.push(count);
  }
  var preset = payload && typeof payload === 'object' && payload.preset ? String(payload.preset) : '';
  var titleSuffix = preset ? ' (ms, ' + preset + ')' : ' (ms)';
  Plotly.react('chart-latency', [{x: x, y: y, type: 'bar', marker: {color: '#2563eb'}}], {
    title: {text: 'Latency Histogram' + titleSuffix, font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: '≤ latency (ms)'},
    yaxis: {title: 'Count'},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent
  }, chartOpts);
}

function updateProbeHistogram(payload) {
  var buckets = payload && Array.isArray(payload.buckets) ? payload.buckets : [];
  var x = [];
  var y = [];
  for (var i = 0; i < buckets.length; i += 1) {
    var bucket = buckets[i];
    if (!bucket) {
      continue;
    }
    var distance = safeNumber(bucket.distance, 0);
    var count = safeNumber(bucket.count, 0);
    x.push(distance);
    y.push(count);
  }
  Plotly.react('chart-probe-bar', [{x: x, y: y, type: 'bar', marker: {color: '#0ea5e9'}}], {
    title: {text: 'Probe Length Distribution', font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: 'Distance'},
    yaxis: {title: 'Count'},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent
  }, chartOpts);
}

function updateHeatmap(payload) {
  var matrix = payload && Array.isArray(payload.matrix) ? payload.matrix : [];
  var total = safeNumber(payload && payload.total, 0);
  var span = safeNumber(payload && payload.slot_span, 1);
  var trace;
  if (matrix.length) {
    trace = {z: matrix, type: 'heatmap', colorscale: 'YlGnBu', hoverongaps: false};
  } else {
    trace = {z: [[0]], type: 'heatmap', colorscale: 'YlGnBu', hoverongaps: false};
  }
  Plotly.react('chart-heatmap', [trace], {
    title: {text: 'Key Distribution Heatmap (total ' + total + ' keys)', font: {size: 16}},
    margin: {l: 45, r: 10, t: 40, b: 40},
    xaxis: {title: 'Segment', zeroline: false},
    yaxis: {title: 'Row', autorange: 'reversed', zeroline: false},
    paper_bgcolor: transparent,
    plot_bgcolor: transparent,
    annotations: [
      {text: 'slot span ×' + span, xref: 'paper', yref: 'paper', x: 0, y: 1.08, showarrow: false, font: {size: 12, color: '#475569'}}
    ]
  }, chartOpts);
}

function updateSummary(tick) {
  var opsByType = tick && typeof tick === 'object' && tick.ops_by_type && typeof tick.ops_by_type === 'object' ? tick.ops_by_type : {};
  document.getElementById('backend').textContent = tick && tick.backend ? String(tick.backend) : '-';
  document.getElementById('ops').textContent = String(safeNumber(tick && tick.ops, 0));
  document.getElementById('puts').textContent = String(safeNumber(opsByType.put, 0));
  document.getElementById('gets').textContent = String(safeNumber(opsByType.get, 0));
  document.getElementById('dels').textContent = String(safeNumber(opsByType.del, 0));
  document.getElementById('migs').textContent = String(safeNumber(tick && tick.migrations, 0));
}

function updateAlerts(alerts) {
  if (!banner) {
    return;
  }
  if (!Array.isArray(alerts) || !alerts.length) {
    banner.textContent = '';
    banner.classList.add('hidden');
    return;
  }
  var pieces = [];
  for (var i = 0; i < alerts.length; i += 1) {
    var alert = alerts[i];
    if (!alert || typeof alert !== 'object') {
      continue;
    }
    var prefix = alert.severity === 'warning' ? '⚠️ ' : '🚩 ';
    var message = alert.message ? String(alert.message) : ((alert.metric ? String(alert.metric) : 'metric') + ' guardrail tripped');
    pieces.push(prefix + message);
  }
  banner.textContent = pieces.join(' | ');
  banner.classList.remove('hidden');
}

function updateEvents(events) {
  var list = document.getElementById('events-list');
  if (!list) {
    return;
  }
  list.textContent = '';
  if (!Array.isArray(events) || !events.length) {
    var empty = document.createElement('li');
    empty.textContent = 'No events recorded yet.';
    list.appendChild(empty);
    return;
  }
  var recent = events.slice(-6).reverse();
  for (var i = 0; i < recent.length; i += 1) {
    var event = recent[i];
    if (!event || typeof event !== 'object') {
      continue;
    }
    var li = document.createElement('li');
    var time = isFinite(event.t) ? Number(event.t).toFixed(2) + 's' : '?';
    var label = event.type ? String(event.type) : 'event';
    var detail = event.backend ? ' backend=' + String(event.backend) : '';
    li.textContent = time + ' • ' + label + detail;
    list.appendChild(li);
  }
}

function computeThroughput(history) {
  if (!Array.isArray(history) || history.length < 2) {
    return null;
  }
  var latest = history[history.length - 1];
  var latestT = safeNumber(latest && latest.t, NaN);
  var latestOps = safeNumber(latest && latest.ops, NaN);
  for (var i = history.length - 2; i >= 0; i -= 1) {
    var prev = history[i];
    var dt = latestT - safeNumber(prev && prev.t, NaN);
    var dOps = latestOps - safeNumber(prev && prev.ops, NaN);
    if (isFinite(dt) && dt > 0 && isFinite(dOps) && dOps >= 0) {
      return dOps / dt;
    }
  }
  return null;
}

function poll() {
  Promise.all([
    fetch('/api/metrics/history?limit=' + MAX_POINTS),
    fetch('/api/metrics'),
    fetch('/api/events?limit=120'),
    fetch('/api/metrics/histogram/latency'),
    fetch('/api/metrics/histogram/probe'),
    fetch('/api/metrics/heatmap')
  ]).then(function(responses) {
    return Promise.all(responses.map(function(response, index) {
      if (!response.ok) {
        if (index === 0) {
          return [];
        }
        return null;
      }
      return response.json();
    }));
  }).then(function(payloads) {
    var history = Array.isArray(payloads[0]) ? payloads[0] : [];
    var latest = payloads[1];
    var events = Array.isArray(payloads[2]) ? payloads[2] : [];
    var latencyPayload = payloads[3] || {};
    var probePayload = payloads[4] || {};
    var heatmapPayload = payloads[5] || {};
    var ticks = history.length ? history : (latest ? [latest] : []);
    if (!ticks.length) {
      return;
    }
    var newest = ticks[ticks.length - 1];
    var seconds = safeNumber(newest && newest.t, NaN);
    pushPoint('load', seconds, safeNumber(newest && newest.load_factor, NaN));
    pushPoint('probe', seconds, safeNumber(newest && newest.avg_probe_estimate, NaN));
    pushPoint('tombstone', seconds, safeNumber(newest && newest.tombstone_ratio, NaN));
    var throughput = computeThroughput(ticks);
    if (throughput !== null) {
      pushPoint('throughput', seconds, throughput);
    }
    updateSummary(newest || {});
    updateAlerts(newest && newest.alerts ? newest.alerts : []);
    updateEvents(events);
    updateLatencyHistogram(latencyPayload);
    updateProbeHistogram(probePayload);
    updateHeatmap(heatmapPayload);
  }).catch(function(err) {
    console.error('metrics poll error', err);
  }).then(function() {
    setTimeout(poll, 2000);
  });
}

poll();
</script>

</body></html>
"""

def start_metrics_server(metrics: Metrics, port: int, host: str = "127.0.0.1") -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _write_body(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _write_json(self, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._write_body(body, "application/json")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/metrics":
                body = metrics.render().encode("utf-8")
                self._write_body(body, "text/plain; version=0.0.4")
                return
            if path == "/api/metrics":
                payload = getattr(metrics, "latest_tick", None) or {}
                self._write_json(payload)
                return
            if path == "/api/events":
                limit = 100
                try:
                    limit = int(parse_qs(parsed.query).get("limit", [str(limit)])[0])
                except ValueError:
                    limit = 100
                limit = max(1, min(limit, 512))
                events = list(getattr(metrics, "events_history", []))[-limit:]
                self._write_json(events)
                return
            if path == "/api/metrics/history":
                history: Optional[Deque[Dict[str, Any]]] = getattr(metrics, "history_buffer", None)
                try:
                    limit = int(parse_qs(parsed.query).get("limit", ["100"])[0])
                except ValueError:
                    limit = 100
                limit = max(1, limit)
                if history:
                    data = list(history)[-limit:]
                else:
                    tick = getattr(metrics, "latest_tick", None)
                    data = [tick] if tick else []
                self._write_json(data)
                return
            if path == "/api/metrics/histogram/latency":
                latest = getattr(metrics, "latest_tick", None) or {}
                hist = latest.get("latency_hist_ms")
                latency_payload: Dict[str, Any] = {
                    "schema": "metrics.latency_histogram.v1",
                    "generated_at": latest.get("t"),
                    "preset": latest.get("latency_hist_preset"),
                    "operations": hist if isinstance(hist, dict) else {},
                }
                self._write_json(latency_payload)
                return
            if path == "/api/metrics/histogram/probe":
                latest = getattr(metrics, "latest_tick", None) or {}
                raw = latest.get("probe_hist")
                buckets: List[Dict[str, int]] = []
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, (list, tuple)) and len(item) == 2:
                            distance, count = item
                        elif isinstance(item, dict):
                            distance = item.get("distance")
                            count = item.get("count")
                        else:
                            continue
                        try:
                            buckets.append({"distance": int(distance), "count": int(count)})
                        except (TypeError, ValueError):
                            continue
                probe_payload = {
                    "schema": "metrics.probe_histogram.v1",
                    "generated_at": latest.get("t"),
                    "buckets": buckets,
                }
                self._write_json(probe_payload)
                return
            if path == "/api/metrics/heatmap":
                latest = getattr(metrics, "latest_tick", None) or {}
                heatmap = getattr(metrics, "key_heatmap", None)
                if not isinstance(heatmap, dict):
                    heatmap = latest.get("key_heatmap") if isinstance(latest, dict) else {}
                heatmap_payload = {
                    "schema": "metrics.key_heatmap.v1",
                    "generated_at": latest.get("t"),
                    "rows": heatmap.get("rows", 0) if isinstance(heatmap, dict) else 0,
                    "cols": heatmap.get("cols", 0) if isinstance(heatmap, dict) else 0,
                    "matrix": heatmap.get("matrix", []) if isinstance(heatmap, dict) else [],
                    "total": heatmap.get("total", 0) if isinstance(heatmap, dict) else 0,
                    "max": heatmap.get("max", 0) if isinstance(heatmap, dict) else 0,
                    "slot_span": heatmap.get("slot_span", 1) if isinstance(heatmap, dict) else 1,
                    "original_slots": heatmap.get("original_slots", 0) if isinstance(heatmap, dict) else 0,
                }
                self._write_json(heatmap_payload)
                return
            if path in {"/", "/index.html"}:
                body = _DASHBOARD_HTML.encode("utf-8")
                self._write_body(body, "text/html; charset=utf-8")
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, fmt: str, *args: Any) -> None:
            return
    server = HTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Metrics server: http://%s:%d/  (dashboard) and /metrics", host.replace("127.0.0.1", "localhost"), port)
    return server

# --------------------------------------------------------------------
# Adaptive wrapper
# --------------------------------------------------------------------
@dataclass
class AdaptiveConfig:
    max_lf_chaining: float = 0.82
    max_group_len: int = 8
    max_avg_probe_robinhood: float = 6.0
    max_tombstone_ratio: float = 0.25
    initial_buckets: int = 64
    groups_per_bucket: int = 8
    initial_capacity_rh: int = 64
    start_backend: str = "chaining"
    incremental_batch: int = 2048
    large_map_warn_threshold: int = 1_000_000
    on_migration: Optional[Callable[[str, str], None]] = None
    on_compaction: Optional[Callable[[], None]] = None  # NEW

def _cfg_to_picklable_dict(cfg: AdaptiveConfig) -> Dict[str, Any]:
    """Strip non-picklable callbacks before saving."""
    d = asdict(cfg)
    d["on_migration"] = None
    d["on_compaction"] = None
    return d

def _cfg_from_dict(d: Dict[str, Any]) -> AdaptiveConfig:
    """Rebuild AdaptiveConfig from a dict (callbacks absent)."""
    # Ignore unknown keys to be forward-compatible.
    keys = {k: d[k] for k in d.keys() if k in AdaptiveConfig().__dict__.keys()}
    cfg = AdaptiveConfig(**keys)  # callbacks default to None
    return cfg

class HybridAdaptiveHashMap:
    """
    Adaptive map: monitors health, migrates incrementally between backends.
    Writes during migration go to the target; reads check target then source.
    Auto-compacts RH based on tombstone ratio. Compactions fire on_compaction().
    """
    def __init__(self, cfg: AdaptiveConfig = AdaptiveConfig()) -> None:
        self.cfg = cfg
        if cfg.start_backend == "chaining":
            self._backend: Any = TwoLevelChainingMap(cfg.initial_buckets, cfg.groups_per_bucket)
            self._name = "chaining"
        else:
            self._backend = RobinHoodMap(cfg.initial_capacity_rh)
            self._name = "robinhood"
        self._migrating_to: Optional[str] = None
        self._migrate_target: Optional[Any] = None
        self._migrate_iter: Optional[Iterator[Tuple[Any, Any]]] = None
        logger.info("Adaptive map started on %s", self._name)

    def __len__(self) -> int: return len(self._backend)
    def backend_name(self) -> str:
        return f"{self._name} -> {self._migrating_to} (migrating)" if self._migrating_to else self._name

    def __getstate__(self) -> Dict[str, Any]:
        while self._migrating_to:
            self._drain_migration()
        return {
            "name": self._name,
            "backend": self._backend,
            "cfg": _cfg_to_picklable_dict(self.cfg),
        }

    def __setstate__(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict) or "backend" not in state or "name" not in state:
            raise TypeError("Bad pickle for HybridAdaptiveHashMap")
        cfg_dict = state.get("cfg", {})
        self.cfg = _cfg_from_dict(cfg_dict) if isinstance(cfg_dict, dict) else AdaptiveConfig()
        self._backend = state["backend"]
        self._name = state["name"]
        self._migrating_to = None
        self._migrate_target = None
        self._migrate_iter = None
        logger.info("Adaptive map restored from pickle (backend=%s)", self._name)

    # Migration internals
    def _begin_migration(self, target: str) -> None:
        size_est = len(self._backend)
        if size_est >= self.cfg.large_map_warn_threshold:
            logger.warning("Starting migration on large map (size=%d). Batch=%d", size_est, self.cfg.incremental_batch)
        logger.info("Preparing migration: %s -> %s", self._name, target)
        self._migrate_target = (TwoLevelChainingMap(self.cfg.initial_buckets, self.cfg.groups_per_bucket)
                                if target == "chaining" else RobinHoodMap(self.cfg.initial_capacity_rh))
        self._migrate_iter = self._backend.items()
        self._migrating_to = target

    def _drain_migration(self) -> None:
        if not self._migrating_to:
            return
        assert self._migrate_iter is not None and self._migrate_target is not None
        moved = 0
        try:
            while moved < self.cfg.incremental_batch:
                k, v = next(self._migrate_iter)
                self._migrate_target.put(k, v)
                moved += 1
        except StopIteration:
            old = self._name
            self._backend = self._migrate_target
            self._name = self._migrating_to or self._name
            self._migrating_to = None
            self._migrate_target = None
            self._migrate_iter = None
            logger.info("Migration complete. Now on backend=%s", self._name)
            if self.cfg.on_migration:
                try:
                    self.cfg.on_migration(old, self._name)
                except Exception as e:
                    logger.error("on_migration callback raised: %s", e)
        except Exception as e:
            logger.exception("Migration error after moving %d items: %s", moved, e)

    def _maintenance(self) -> None:
        self._drain_migration()
        if self._migrating_to:
            return
        if isinstance(self._backend, TwoLevelChainingMap):
            lf = self._backend.load_factor()
            mg = self._backend.max_group_len()
            if lf > self.cfg.max_lf_chaining or mg > self.cfg.max_group_len:
                self._begin_migration("robinhood")
        elif isinstance(self._backend, RobinHoodMap):
            ap = self._backend.avg_probe_estimate()
            if ap > self.cfg.max_avg_probe_robinhood:
                self._begin_migration("chaining")
            else:
                if self._backend.tombstone_ratio() > self.cfg.max_tombstone_ratio:
                    logger.info("Auto-compacting RobinHoodMap (tombstone_ratio=%.3f)", self._backend.tombstone_ratio())
                    self._backend.compact()
                    if self.cfg.on_compaction:
                        try:
                            self.cfg.on_compaction()
                        except Exception as e:
                            logger.error("on_compaction callback raised: %s", e)

    # Public API
    def put(self, k: Any, v: Any) -> None:
        self._drain_migration()
        (self._migrate_target or self._backend).put(k, v)
        self._maintenance()

    def get(self, k: Any) -> Optional[Any]:
        self._drain_migration()
        if self._migrate_target is not None:
            v = self._migrate_target.get(k)
            if v is not None:
                return v
        return self._backend.get(k)

    def delete(self, k: Any) -> bool:
        self._drain_migration()
        if self._migrate_target is not None and self._migrate_target.delete(k):
            return True
        ok = self._backend.delete(k)
        self._maintenance()
        return ok

    def items(self) -> Iterable[Tuple[Any, Any]]:
        while self._migrating_to:
            self._drain_migration()
        return self._backend.items()

    # Snapshot (callbacks stripped)
    def save(self, filepath: str, compress: bool = False) -> None:
        while self._migrating_to:
            self._drain_migration()
        state = {
            "name": self._name,
            "backend": self._backend,
            "cfg": _cfg_to_picklable_dict(self.cfg),  # callbacks removed
        }
        with _open_for_write(filepath, compress) as f:
            pickle.dump(state, f)

    @staticmethod
    def load(filepath: str) -> "HybridAdaptiveHashMap":
        with _open_for_read(filepath) as f:
            state = pickle.load(f)
        if not isinstance(state, dict) or "backend" not in state or "name" not in state:
            raise TypeError("Snapshot is not a HybridAdaptiveHashMap")
        cfg_dict = state.get("cfg", {})
        cfg = _cfg_from_dict(cfg_dict) if isinstance(cfg_dict, dict) else AdaptiveConfig()
        obj = HybridAdaptiveHashMap(cfg)
        obj._backend = state["backend"]
        obj._name = state["name"]
        obj._migrating_to = None
        obj._migrate_target = None
        obj._migrate_iter = None
        # Note: callbacks are intentionally not restored from snapshot.
        return obj

# --------------------------------------------------------------------
# Metrics helpers
# --------------------------------------------------------------------
class MetricsSink:
    def __init__(
        self,
        metrics: Optional[Metrics],
        events: Optional[List[Dict[str, Any]]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.metrics = metrics
        self.events = events
        self.clock = clock or (lambda: 0.0)

    def inc_migrations(self) -> None:
        if self.metrics:
            self.metrics.migrations_total += 1

    def inc_compactions(self) -> None:
        if self.metrics:
            self.metrics.compactions_total += 1

    def record_event(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.events is None:
            return
        event = {"type": kind, "t": self.clock()}
        if payload:
            event.update(payload)
        self.events.append(event)

    def attach(self, m: Any) -> None:
        if isinstance(m, HybridAdaptiveHashMap):
            def on_migration(old: str, new: str) -> None:
                self.inc_migrations()
                self.record_event("switch", {"from": old, "to": new})

            def on_compaction() -> None:
                self.inc_compactions()
                self.record_event("compaction", {"backend": m.backend_name()})

            m.cfg.on_migration = on_migration
            m.cfg.on_compaction = on_compaction


def _reattach_runtime_callbacks(m: Any, sink: MetricsSink) -> None:
    """Reattach metrics hooks for adaptive maps that come from snapshots."""
    sink.attach(m)

def build_map(
    mode: str,
    metrics: Optional[Metrics] = None,
    *,
    sink: Optional[MetricsSink] = None,
) -> Any:
    sink = sink or MetricsSink(metrics)

    def make_adaptive() -> HybridAdaptiveHashMap:
        policy = APP_CONFIG.adaptive
        cfg = AdaptiveConfig(
            start_backend=policy.start_backend,
            initial_buckets=policy.initial_buckets,
            groups_per_bucket=policy.groups_per_bucket,
            initial_capacity_rh=policy.initial_capacity_rh,
            incremental_batch=policy.incremental_batch,
            max_lf_chaining=policy.max_lf_chaining,
            max_group_len=policy.max_group_len,
            max_avg_probe_robinhood=policy.max_avg_probe_robinhood,
            max_tombstone_ratio=policy.max_tombstone_ratio,
            large_map_warn_threshold=policy.large_map_warn_threshold,
        )
        m = HybridAdaptiveHashMap(cfg)
        sink.attach(m)
        return m
    if mode == "fast-insert":
        chaining = TwoLevelChainingMap(initial_buckets=64, groups_per_bucket=8)
        sink.attach(chaining)
        return chaining
    if mode in ("fast-lookup", "memory-tight"):
        robin = RobinHoodMap(initial_capacity=64)
        sink.attach(robin)
        return robin
    if mode == "adaptive":
        return make_adaptive()
    raise ValueError(f"unknown mode: {mode}")

def sample_metrics(m: Any, metrics: Metrics) -> None:
    metrics.backend_name = getattr(m, "backend_name", lambda: type(m).__name__)()
    metrics.load_factor = 0.0
    metrics.max_group_len = 0.0
    metrics.avg_probe_estimate = 0.0
    metrics.tombstone_ratio = 0.0
    if isinstance(m, TwoLevelChainingMap):
        metrics.load_factor = m.load_factor()
        metrics.max_group_len = float(m.max_group_len())
    elif isinstance(m, RobinHoodMap):
        metrics.load_factor = m.load_factor()
        metrics.avg_probe_estimate = float(m.avg_probe_estimate())
        metrics.tombstone_ratio = float(m.tombstone_ratio())
    elif isinstance(m, HybridAdaptiveHashMap):
        metrics.backend_name = m.backend_name()
        backend = getattr(m, "_backend", None)
        if isinstance(backend, TwoLevelChainingMap):
            metrics.load_factor = backend.load_factor()
            metrics.max_group_len = float(backend.max_group_len())
        elif isinstance(backend, RobinHoodMap):
            metrics.load_factor = backend.load_factor()
            metrics.avg_probe_estimate = float(backend.avg_probe_estimate())
            metrics.tombstone_ratio = float(backend.tombstone_ratio())


def collect_probe_histogram(m: Any) -> List[List[int]]:
    histogram: Dict[int, int] = defaultdict(int)

    def record(rh: RobinHoodMap) -> None:
        for idx, slot in enumerate(rh._table):
            if isinstance(slot, _RHEntry):
                ideal = rh._idx(hash(slot.key))
                dist = rh._probe_distance(ideal, idx)
                histogram[int(dist)] += 1

    if isinstance(m, RobinHoodMap):
        record(m)
    elif isinstance(m, HybridAdaptiveHashMap):
        backend = getattr(m, "_backend", None)
        if isinstance(backend, RobinHoodMap):
            record(backend)
    return [[distance, count] for distance, count in sorted(histogram.items())]


def collect_key_heatmap(m: Any, target_cols: int = 32, max_cells: int = 512) -> Dict[str, Any]:
    """Aggregate key distribution into a compact heatmap payload."""

    def key_counts_for_map(obj: Any) -> List[int]:
        if isinstance(obj, TwoLevelChainingMap):
            return [len(group) for bucket in obj._buckets for group in bucket]
        if isinstance(obj, RobinHoodMap):
            return [1 if isinstance(slot, _RHEntry) else 0 for slot in obj._table]
        if isinstance(obj, HybridAdaptiveHashMap):
            backend = getattr(obj, "_backend", None)
            if backend is not None:
                return key_counts_for_map(backend)
        return []

    base_counts = key_counts_for_map(m)
    original_slots = len(base_counts)
    if not base_counts:
        return {
            "rows": 0,
            "cols": 0,
            "matrix": [],
            "max": 0,
            "total": 0,
            "slot_span": 1,
            "original_slots": original_slots,
        }

    total = sum(base_counts)
    # Down-sample into at most max_cells buckets to keep payload manageable.
    target_cells = max(1, max_cells)
    group_width = max(1, math.ceil(original_slots / target_cells))
    aggregated: List[int] = []
    for idx in range(0, original_slots, group_width):
        aggregated.append(sum(base_counts[idx : idx + group_width]))

    cols = max(1, min(target_cols, len(aggregated)))
    rows = math.ceil(len(aggregated) / cols)
    padded_length = rows * cols
    if len(aggregated) < padded_length:
        aggregated.extend([0] * (padded_length - len(aggregated)))
    matrix = [aggregated[r * cols : (r + 1) * cols] for r in range(rows)]

    return {
        "rows": rows,
        "cols": cols,
        "matrix": matrix,
        "max": max(aggregated) if aggregated else 0,
        "total": total,
        "slot_span": group_width,
        "original_slots": original_slots,
    }

# --------------------------------------------------------------------
# Reservoir sampling for latency percentiles
# --------------------------------------------------------------------
DEFAULT_LATENCY_BUCKET_BOUNDS_MS: Tuple[float, ...] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    math.inf,
)

MICRO_LATENCY_BUCKET_BOUNDS_MS: Tuple[float, ...] = (
    0.001,
    0.002,
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    math.inf,
)

LATENCY_BUCKET_PRESETS_MS: Dict[str, Tuple[float, ...]] = {
    "default": DEFAULT_LATENCY_BUCKET_BOUNDS_MS,
    "micro": MICRO_LATENCY_BUCKET_BOUNDS_MS,
}


def resolve_latency_bucket_bounds(name: str) -> Tuple[str, Tuple[float, ...]]:
    """Return canonical preset key + bounds for latency histograms."""

    key = (name or "default").strip().lower()
    preset = LATENCY_BUCKET_PRESETS_MS.get(key)
    if preset is None:
        raise ValueError(f"Unknown latency bucket preset: {name}")
    return key, preset


def _format_float(value: float) -> str:
    text = f"{value:.6f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_app_config_to_toml(cfg: AppConfig) -> str:
    adaptive = cfg.adaptive
    watchdog = cfg.watchdog
    lines = [
        "[adaptive]",
        f'start_backend = "{adaptive.start_backend}"',
        f"initial_buckets = {adaptive.initial_buckets}",
        f"groups_per_bucket = {adaptive.groups_per_bucket}",
        f"initial_capacity_rh = {adaptive.initial_capacity_rh}",
        f"incremental_batch = {adaptive.incremental_batch}",
        f"max_lf_chaining = {_format_float(adaptive.max_lf_chaining)}",
        f"max_group_len = {adaptive.max_group_len}",
        f"max_avg_probe_robinhood = {_format_float(adaptive.max_avg_probe_robinhood)}",
        f"max_tombstone_ratio = {_format_float(adaptive.max_tombstone_ratio)}",
        f"large_map_warn_threshold = {adaptive.large_map_warn_threshold}",
        "",
        "[watchdog]",
        f"enabled = {str(watchdog.enabled).lower()}",
    ]

    if watchdog.load_factor_warn is not None:
        lines.append(f"load_factor_warn = {_format_float(watchdog.load_factor_warn)}")
    else:
        lines.append('load_factor_warn = "none"')
    if watchdog.avg_probe_warn is not None:
        lines.append(f"avg_probe_warn = {_format_float(watchdog.avg_probe_warn)}")
    else:
        lines.append('avg_probe_warn = "none"')
    if watchdog.tombstone_ratio_warn is not None:
        lines.append(f"tombstone_ratio_warn = {_format_float(watchdog.tombstone_ratio_warn)}")
    else:
        lines.append('tombstone_ratio_warn = "none"')

    return "\n".join(lines) + "\n"


def run_config_wizard(
    outfile: str,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> Path:
    """Interactive CLI wizard that writes a TOML config file."""

    cfg = AppConfig()

    def prompt_choice(prompt: str, default: str, choices: Tuple[str, ...]) -> str:
        choice_str = "/".join(choices)
        while True:
            raw = input_fn(f"{prompt} ({choice_str}) [{default}]: ").strip().lower()
            if not raw:
                return default
            if raw in choices:
                return raw
            print_fn(f"Please enter one of: {', '.join(choices)}")

    def prompt_int(prompt: str, default: int, validator: Optional[Callable[[int], bool]] = None) -> int:
        while True:
            raw = input_fn(f"{prompt} [{default}]: ").strip()
            if not raw:
                return default
            try:
                value = int(raw)
            except ValueError:
                print_fn("Enter a whole number.")
                continue
            if validator and not validator(value):
                print_fn("Value rejected by validation; try again.")
                continue
            return value

    def prompt_float(prompt: str, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
        while True:
            raw = input_fn(f"{prompt} [{_format_float(default)}]: ").strip()
            if not raw:
                return default
            try:
                value = float(raw)
            except ValueError:
                print_fn("Enter a numeric value.")
                continue
            if min_val is not None and value < min_val:
                print_fn(f"Value must be ≥ {min_val}.")
                continue
            if max_val is not None and value > max_val:
                print_fn(f"Value must be ≤ {max_val}.")
                continue
            return value

    def prompt_optional_float(prompt: str, default: Optional[float], min_val: Optional[float], max_val: Optional[float]) -> Optional[float]:
        while True:
            default_repr = "null" if default is None else _format_float(default)
            raw = input_fn(f"{prompt} [{default_repr}]: ").strip().lower()
            if not raw:
                return default
            if raw in {"none", "null", "off"}:
                return None
            try:
                value = float(raw)
            except ValueError:
                print_fn("Enter a numeric value or 'none'.")
                continue
            if min_val is not None and value < min_val:
                print_fn(f"Value must be ≥ {min_val}.")
                continue
            if max_val is not None and value > max_val:
                print_fn(f"Value must be ≤ {max_val}.")
                continue
            return value

    def prompt_bool(prompt: str, default: bool) -> bool:
        default_hint = "Y/n" if default else "y/N"
        while True:
            raw = input_fn(f"{prompt} [{default_hint}]: ").strip().lower()
            if not raw:
                return default
            if raw in {"y", "yes", "1", "true"}:
                return True
            if raw in {"n", "no", "0", "false"}:
                return False
            print_fn("Please answer yes or no.")

    print_fn("Adaptive Hash Map Configuration Wizard")
    print_fn("Press Enter to keep defaults; type 'none' to disable optional thresholds.\n")

    adaptive = cfg.adaptive
    watchdog = cfg.watchdog

    adaptive.start_backend = prompt_choice(
        "Start backend",
        adaptive.start_backend,
        ("chaining", "robinhood"),
    )

    def is_power_of_two(value: int) -> bool:
        return value > 0 and value & (value - 1) == 0

    adaptive.initial_buckets = prompt_int("Initial buckets (power of two)", adaptive.initial_buckets, is_power_of_two)
    adaptive.groups_per_bucket = prompt_int("Groups per bucket (power of two)", adaptive.groups_per_bucket, is_power_of_two)
    adaptive.initial_capacity_rh = prompt_int("Initial capacity (Robin Hood, power of two)", adaptive.initial_capacity_rh, is_power_of_two)
    adaptive.incremental_batch = prompt_int("Incremental batch size", adaptive.incremental_batch, lambda v: v > 0)
    adaptive.max_lf_chaining = prompt_float("Max load factor before migrating (0-1]", adaptive.max_lf_chaining, 0.01, 1.0)
    adaptive.max_group_len = prompt_int("Max chaining group length", adaptive.max_group_len, lambda v: v > 0)
    adaptive.max_avg_probe_robinhood = prompt_float("Max average probe distance (Robin Hood)", adaptive.max_avg_probe_robinhood, 0.1, None)
    adaptive.max_tombstone_ratio = prompt_float("Max tombstone ratio before compaction (0-1)", adaptive.max_tombstone_ratio, 0.0, 1.0)
    adaptive.large_map_warn_threshold = prompt_int("Large map warning threshold (keys)", adaptive.large_map_warn_threshold, lambda v: v >= 0)

    print_fn("")
    watchdog.enabled = prompt_bool("Enable watchdog alerts", watchdog.enabled)
    watchdog.load_factor_warn = prompt_optional_float("Watchdog load factor warning threshold", watchdog.load_factor_warn, 0.0, 1.0)
    watchdog.avg_probe_warn = prompt_optional_float("Watchdog avg probe warning threshold", watchdog.avg_probe_warn, 0.0, None)
    watchdog.tombstone_ratio_warn = prompt_optional_float("Watchdog tombstone ratio warning threshold", watchdog.tombstone_ratio_warn, 0.0, 1.0)

    cfg.validate()

    toml_text = format_app_config_to_toml(cfg)
    out_path = Path(outfile).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(toml_text, encoding="utf-8")

    print_fn("")
    print_fn(f"Configuration written to {out_path}")
    print_fn("Pass `--config` or set ADHASH_CONFIG to use it.")
    return out_path


class Reservoir:
    """
    Fixed-size reservoir with uniform random replacement.
    Stores float milliseconds for sampled operation latencies.
    """
    __slots__ = ("k", "buf", "n", "rng")

    def __init__(self, k: int = 1000, seed: int = 0xC0FFEE) -> None:
        self.k = max(1, k)
        self.buf: List[float] = []
        self.n = 0  # total seen
        self.rng = random.Random(seed)

    def offer(self, value_ms: float) -> None:
        """Offer a sample; replaces random entry after reservoir is full."""
        self.n += 1
        if len(self.buf) < self.k:
            self.buf.append(value_ms)
            return
        j = self.rng.randrange(self.n)
        if j < self.k:
            self.buf[j] = value_ms

    def percentiles(self, ps: List[float]) -> Dict[str, float]:
        """Return percentile map { 'p50': .., 'p90': .., ... } from reservoir."""
        if not self.buf:
            return {f"p{int(p*100)}": 0.0 for p in ps}
        data = sorted(self.buf)
        out: Dict[str, float] = {}
        for p in ps:
            idx = min(len(data) - 1, max(0, int(round(p * (len(data) - 1)))))
            out[f"p{int(p*100)}"] = data[idx]
        return out

# --------------------------------------------------------------------
# Ops runner / profiler / generator
# --------------------------------------------------------------------
def run_op(m: Any, op: str, key: Optional[str], value: Optional[str],
           metrics: Optional[Metrics] = None) -> Optional[str]:
    if op == "put":
        assert key is not None and value is not None
        m.put(key, value)
        if metrics:
            metrics.puts_total += 1
    elif op == "get":
        assert key is not None
        v = m.get(key)
        if metrics:
            metrics.gets_total += 1
        return "" if v is None else str(v)
    elif op == "del":
        assert key is not None
        ok = m.delete(key)
        if metrics:
            metrics.dels_total += 1
        return "1" if ok else "0"
    elif op == "items":
        return "\n".join(f"{k},{v}" for k, v in m.items())
    else:
        raise ValueError(f"unknown op: {op}")
    return "OK"


def _parse_items_output(raw: Optional[str]) -> List[Dict[str, str]]:
    if not raw:
        return []
    items: List[Dict[str, str]] = []
    for line in raw.splitlines():
        if not line:
            continue
        if "," in line:
            key, value = line.split(",", 1)
        else:
            key, value = line, ""
        items.append({"key": key, "value": value})
    return items

def profile_csv(path: str, sample_limit: int = 5000) -> str:
    def load_ops():
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            for i, row in enumerate(r):
                if sample_limit and i >= sample_limit:
                    break
                yield row["op"], row["key"], row.get("value") or None
    ops = list(load_ops())
    candidates: Dict[str, Any] = {
        "fast-insert": build_map("fast-insert"),
        "fast-lookup": build_map("fast-lookup"),
    }
    results: Dict[str, float] = {}
    for label, impl in candidates.items():
        start = time.perf_counter()
        for op, k, v in ops:
            if op == "items":
                continue
            run_op(impl, op, k, v)
        elapsed = time.perf_counter() - start
        results[label] = elapsed
        logger.info("Profile %s: %.6f s over %d ops", label, elapsed, len(ops))
    pick = min(results, key=lambda name: results[name])
    logger.info("Profile pick: %s", pick)
    return pick


@guard_cli
def _cmd_put(args: argparse.Namespace) -> int:
    m = build_map(args.mode)
    out = run_op(m, "put", args.key, args.value)
    data = {"mode": args.mode, "key": args.key, "value": args.value}
    if out is not None:
        data["result"] = out
    emit_success("put", text=out, data=data)
    return int(Exit.OK)


@guard_cli
def _cmd_get(args: argparse.Namespace) -> int:
    m = build_map(args.mode)
    out = run_op(m, "get", args.key, None)
    value = out if out not in {None, ""} else None
    data = {
        "mode": args.mode,
        "key": args.key,
        "found": bool(value),
        "value": value,
    }
    emit_success("get", text=out, data=data)
    return int(Exit.OK)


@guard_cli
def _cmd_del(args: argparse.Namespace) -> int:
    m = build_map(args.mode)
    out = run_op(m, "del", args.key, None)
    deleted = out == "1"
    data = {"mode": args.mode, "key": args.key, "deleted": deleted}
    emit_success("del", text=out, data=data)
    return int(Exit.OK)


@guard_cli
def _cmd_items(args: argparse.Namespace) -> int:
    m = build_map(args.mode)
    out = run_op(m, "items", None, None)
    items = _parse_items_output(out)
    data = {"mode": args.mode, "count": len(items), "items": items}
    emit_success("items", text=out, data=data)
    return int(Exit.OK)


@guard_cli
def _cmd_profile(args: argparse.Namespace) -> int:
    pick = profile_csv(args.csv)
    emit_success("profile", text=pick, data={"csv": args.csv, "recommended_mode": pick})
    if args.then:
        return main(["--mode", pick] + args.then)
    return int(Exit.OK)


@guard_cli
def _cmd_generate(args: argparse.Namespace) -> int:
    try:
        generate_csv(args.outfile, args.ops, args.read_ratio, args.key_skew,
                     args.key_space, args.seed, del_ratio_within_writes=args.del_ratio,
                     adversarial_ratio=args.adversarial_ratio, adversarial_lowbits=args.adversarial_lowbits)
    except OSError as exc:
        raise IOErrorEnvelope(str(exc)) from exc
    logger.info("Wrote workload CSV: %s", args.outfile)
    emit_success(
        "generate-csv",
        data={
            "outfile": args.outfile,
            "ops": args.ops,
            "read_ratio": args.read_ratio,
            "key_skew": args.key_skew,
            "key_space": args.key_space,
            "seed": args.seed,
            "del_ratio": args.del_ratio,
            "adversarial_ratio": args.adversarial_ratio,
            "adversarial_lowbits": args.adversarial_lowbits,
        },
    )
    return int(Exit.OK)


@guard_cli
def _cmd_run_csv(args: argparse.Namespace) -> int:
    result = run_csv(
        args.csv,
        args.mode,
        metrics_port=args.metrics_port,
        snapshot_in=args.snapshot_in,
        snapshot_out=args.snapshot_out,
        compress_out=args.compress,
        compact_interval=args.compact_interval,
        json_summary_out=args.json_summary_out,
        latency_sample_k=args.latency_sample_k,
        latency_sample_every=args.latency_sample_every,
        latency_bucket_preset=args.latency_buckets,
        metrics_out_dir=args.metrics_out_dir,
        metrics_max_ticks=args.metrics_max_ticks,
        dry_run=args.dry_run,
        csv_max_rows=args.csv_max_rows,
        csv_max_bytes=args.csv_max_bytes,
    )
    emit_success("run-csv", data=result)
    return int(Exit.OK)


@guard_cli
def _cmd_config_wizard(args: argparse.Namespace) -> int:
    out_path = run_config_wizard(args.outfile)
    emit_success(
        "config-wizard",
        text=f"Configuration written to {out_path}",
        data={"outfile": str(out_path)},
    )
    return int(Exit.OK)


@guard_cli
def _cmd_mission_control(args: argparse.Namespace) -> int:
    from adhash.mission_control.app import run_mission_control

    return int(run_mission_control([]))


@guard_cli
def _cmd_serve(args: argparse.Namespace) -> int:
    history_limit = args.history_limit if args.history_limit and args.history_limit > 0 else 360
    history: Deque[Dict[str, Any]] = deque(maxlen=history_limit)

    metrics = Metrics()
    metrics.history_buffer = history
    server = start_metrics_server(metrics, args.port, host=args.host)
    logger.info(
        "Serve mode: dashboard available at http://%s:%d/ (source=%s, follow=%s)",
        args.host,
        args.port,
        args.source or "none",
        args.follow,
    )

    def ingest(tick: Dict[str, Any]) -> None:
        apply_tick_to_metrics(metrics, tick)

    if args.source:
        source_path = Path(args.source).expanduser().resolve()

        def worker_target() -> None:
            _stream_metrics_file(
                source_path,
                follow=args.follow,
                callback=ingest,
                poll_interval=args.poll_interval,
            )

        threading.Thread(target=worker_target, daemon=True).start()

    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        logger.info("Shutting down serve mode")
    finally:
        try:
            server.shutdown()
        finally:
            server.server_close()
    return int(Exit.OK)


@guard_cli
def _cmd_compact_snapshot(args: argparse.Namespace) -> int:
    try:
        rh = RobinHoodMap.load(args.infile)
    except FileNotFoundError as exc:
        raise IOErrorEnvelope(str(exc)) from exc
    before_size = len(rh)
    before_cap = rh._cap
    before_tombstone = rh.tombstone_ratio()
    logger.info(
        "Loaded RobinHoodMap snapshot cap=%d size=%d tombstones≈%.2f%%",
        rh._cap,
        len(rh),
        rh.tombstone_ratio() * 100.0,
    )
    rh.compact()
    after_size = len(rh)
    after_tombstone = rh.tombstone_ratio()
    try:
        rh.save(args.outfile, compress=args.compress)
    except OSError as exc:
        raise IOErrorEnvelope(str(exc)) from exc
    logger.info(
        "Wrote compacted snapshot: %s cap=%d size=%d tombstones≈%.2f%%",
        args.outfile,
        rh._cap,
        len(rh),
        rh.tombstone_ratio() * 100.0,
    )
    emit_success(
        "compact-snapshot",
        data={
            "infile": args.infile,
            "outfile": args.outfile,
            "compress": bool(args.compress),
            "before": {
                "size": before_size,
                "capacity": before_cap,
                "tombstone_ratio": before_tombstone,
            },
            "after": {
                "size": after_size,
                "capacity": rh._cap,
                "tombstone_ratio": after_tombstone,
            },
        },
    )
    return int(Exit.OK)


@guard_cli
def _cmd_verify_snapshot(args: argparse.Namespace) -> int:
    if OUTPUT_JSON:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = verify_snapshot(
                args.infile,
                verbose=args.verbose,
                repair=args.repair,
                repair_out=args.outfile,
            )
        if rc != 0:
            raise InvariantError("Snapshot verification failed")
        messages = [line for line in buffer.getvalue().splitlines() if line.strip()]
        emit_success(
            "verify-snapshot",
            data={
                "infile": args.infile,
                "repaired": bool(args.repair),
                "messages": messages,
            },
        )
        return int(Exit.OK)

    rc = verify_snapshot(args.infile, verbose=args.verbose,
                         repair=args.repair, repair_out=args.outfile)
    if rc != 0:
        raise InvariantError("Snapshot verification failed")
    emit_success(
        "verify-snapshot",
        data={"infile": args.infile, "repaired": bool(args.repair)},
    )
    return int(Exit.OK)

def _zipf_sampler(n_keys: int, skew: float, rng: random.Random) -> Callable[[], int]:
    if n_keys <= 0:
        raise ValueError("n_keys must be > 0")
    if skew <= 0.0:
        return lambda: rng.randrange(n_keys)
    weights = [1.0 / ((k + 1) ** skew) for k in range(n_keys)]
    total = sum(weights)
    cdf: List[float] = []
    acc = 0.0
    for w in weights:
        acc += w / total
        cdf.append(acc)
    def sample() -> int:
        x = rng.random()
        lo, hi = 0, n_keys - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if x <= cdf[mid]:
                hi = mid
            else:
                lo = mid + 1
        return lo
    return sample

def _adversarialize_key(base_idx: int, lowbits: int) -> int:
    if lowbits <= 0:
        return base_idx
    mask = (1 << lowbits) - 1
    return (base_idx & ~mask)

def generate_csv(out_path: str, ops: int, read_ratio: float, key_skew: float,
                 key_space: int, seed: int, del_ratio_within_writes: float = 0.2,
                 adversarial_ratio: float = 0.0, adversarial_lowbits: int = 6) -> None:
    if ops <= 0:
        raise ValueError("ops must be > 0")
    if not (0.0 <= read_ratio <= 1.0):
        raise ValueError("read_ratio must be in [0,1]")
    if key_space <= 0:
        raise ValueError("key_space must be > 0")
    if not (0.0 <= del_ratio_within_writes < 1.0):
        raise ValueError("del_ratio_within_writes in [0,1)")
    if not (0.0 <= adversarial_ratio <= 1.0):
        raise ValueError("adversarial_ratio in [0,1]")
    rng = random.Random(seed)
    sample_key_idx = _zipf_sampler(key_space, key_skew, rng)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["op", "key", "value"])
        for _ in range(ops):
            idx = sample_key_idx()
            if rng.random() < adversarial_ratio:
                idx = _adversarialize_key(idx, adversarial_lowbits)
            key = f"K{idx}"
            if rng.random() < read_ratio:
                w.writerow(["get", key, ""])
            else:
                if rng.random() < del_ratio_within_writes:
                    w.writerow(["del", key, ""])
                else:
                    w.writerow(["put", key, str(rng.randint(0, 1_000_000))])

# --------------------------------------------------------------------
# Runner with proactive compaction, JSON summary (+ percentiles), snapshots
# --------------------------------------------------------------------
def run_csv(path: str, mode: str, metrics_port: Optional[int] = None,
            snapshot_in: Optional[str] = None, snapshot_out: Optional[str] = None,
            compress_out: bool = False, compact_interval: Optional[float] = None,
            json_summary_out: Optional[str] = None,
            latency_sample_k: int = 1000, latency_sample_every: int = 128,
            latency_bucket_preset: str = "default",
            metrics_out_dir: Optional[str] = None,
            metrics_max_ticks: Optional[int] = None,
            dry_run: bool = False,
            csv_max_rows: int = DEFAULT_CSV_MAX_ROWS,
            csv_max_bytes: int = DEFAULT_CSV_MAX_BYTES) -> Dict[str, Any]:
    """
    Replay operations from a CSV workload. Exposes live metrics, writes
    machine-readable summaries for CI pipelines, and returns a structured
    result payload for callers.

    Percentile latency is estimated by sampling every Nth operation (N=latency_sample_every),
    feeding per-op elapsed time (ms) into fixed-size reservoirs (K=latency_sample_k).
    """
    csv_hint = "See docs/workload_schema.md"
    csv_path = Path(path)
    row_counter = 0

    if csv_max_bytes and csv_max_bytes > 0:
        try:
            size_bytes = csv_path.stat().st_size
        except FileNotFoundError as exc:
            raise IOErrorEnvelope(str(exc)) from exc
        if size_bytes > csv_max_bytes:
            raise BadInputError(
                f"CSV file is {size_bytes} bytes which exceeds limit {csv_max_bytes}",
                hint=csv_hint,
            )
    else:
        size_bytes = None

    preset_from_env = os.getenv("ADHASH_LATENCY_BUCKETS")
    requested_preset = preset_from_env or latency_bucket_preset
    try:
        latency_hist_preset, latency_bucket_bounds_tuple = resolve_latency_bucket_bounds(requested_preset)
    except ValueError:
        latency_hist_preset, latency_bucket_bounds_tuple = resolve_latency_bucket_bounds("default")
        logger.warning(
            "Unknown latency bucket preset '%s'; falling back to 'default'",
            requested_preset,
        )
    latency_bucket_bounds = list(latency_bucket_bounds_tuple)

    def load_ops(validate_only: bool = False):
        nonlocal row_counter
        try:
            with open(path, newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                required = {"op", "key", "value"}
                header = {fn.strip() for fn in fieldnames}
                missing = required - header
                if missing:
                    raise BadInputError(
                        f"Missing header columns: {', '.join(sorted(missing))}", hint=csv_hint
                    )
                unexpected = header - required
                if unexpected:
                    raise BadInputError(
                        f"Unexpected column(s) in header: {', '.join(sorted(unexpected))}",
                        hint=csv_hint,
                    )
                for row in reader:
                    row_counter += 1
                    if csv_max_rows and csv_max_rows > 0 and row_counter > csv_max_rows:
                        raise BadInputError(
                            f"CSV row limit exceeded ({row_counter} > {csv_max_rows})",
                            hint=csv_hint,
                        )
                    op_raw = (row.get("op") or "").strip().lower()
                    key = (row.get("key") or "").strip()
                    value = row.get("value")
                    line_no = reader.line_num
                    if not op_raw:
                        raise BadInputError(f"Missing op at line {line_no}", hint=csv_hint)
                    if op_raw not in {"put", "get", "del"}:
                        raise BadInputError(f"Unknown op '{op_raw}' at line {line_no}", hint=csv_hint)
                    if not key:
                        raise BadInputError(f"Missing key at line {line_no}", hint=csv_hint)
                    if op_raw == "put":
                        if value is None or value.strip() == "":
                            raise BadInputError(
                                f"PUT missing value at line {line_no}", hint=csv_hint
                            )
                    else:
                        value = None
                    if validate_only:
                        continue
                    yield op_raw, key, value
        except FileNotFoundError as exc:
            raise IOErrorEnvelope(str(exc)) from exc
        except BadInputError:
            raise
        except OSError as exc:
            raise IOErrorEnvelope(str(exc)) from exc
        except Exception as exc:
            raise BadInputError(str(exc), hint=csv_hint) from exc

    if dry_run:
        if size_bytes is None:
            try:
                size_bytes = csv_path.stat().st_size
            except FileNotFoundError:
                size_bytes = 0
        for _ in load_ops(validate_only=True):
            pass
        size_mb = (size_bytes or 0) / (1024 * 1024)
        logger.info(
            "CSV validation successful (%d rows, %.2f MiB): %s",
            row_counter,
            size_mb,
            path,
        )
        return {
            "status": "validated",
            "csv": str(path),
            "mode": mode,
            "rows": row_counter,
            "size_bytes": size_bytes,
            "size_mib": size_mb,
        }

    run_result: Dict[str, Any] = {
        "status": "running",
        "csv": str(path),
        "mode": mode,
    }
    if metrics_port is not None:
        run_result["metrics_port"] = metrics_port
    if snapshot_in:
        run_result["snapshot_in"] = snapshot_in
    if snapshot_out:
        run_result["snapshot_out"] = snapshot_out
    if json_summary_out:
        run_result["json_summary_out"] = json_summary_out
    if metrics_out_dir:
        run_result["metrics_out_dir"] = metrics_out_dir
    if compact_interval is not None:
        run_result["compact_interval"] = compact_interval

    history_max = metrics_max_ticks if metrics_max_ticks and metrics_max_ticks > 0 else 100
    history_buffer: Deque[Dict[str, Any]] = deque(maxlen=history_max)

    metrics = Metrics()
    metrics.history_buffer = history_buffer
    server = start_metrics_server(metrics, metrics_port) if metrics_port is not None else None

    metrics_file = None
    metrics_path: Optional[Path] = None
    if metrics_out_dir:
        out_dir = Path(metrics_out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_mode = "w+" if metrics_max_ticks and metrics_max_ticks > 0 else "a"
        metrics_path = out_dir / "metrics.ndjson"
        metrics_file = metrics_path.open(file_mode, encoding="utf-8")

    events: List[Dict[str, Any]] = []
    start = time.perf_counter()
    def clock() -> float:
        return time.perf_counter() - start
    sink = MetricsSink(metrics, events, clock)
    watchdog = ThresholdWatchdog(APP_CONFIG.watchdog)

    if snapshot_in:
        try:
            snap = _load_snapshot_any(snapshot_in)
        except ValueError as exc:
            raise InvariantError(f"Failed to load snapshot: {exc}") from exc
        if isinstance(snap, (TwoLevelChainingMap, RobinHoodMap, HybridAdaptiveHashMap)):
            m = snap
        elif isinstance(snap, dict) and "backend" in snap:
            m = HybridAdaptiveHashMap.load(snapshot_in)
        else:
            raise PolicyError("Unsupported snapshot format")
        logger.info("Loaded snapshot from %s (type=%s)", snapshot_in, type(m).__name__)
        sink.attach(m)
    else:
        m = build_map(mode, metrics=metrics, sink=sink)

    _reattach_runtime_callbacks(m, sink)

    want_latency = json_summary_out is not None and latency_sample_k > 0 and latency_sample_every > 0
    overall_res = Reservoir(k=latency_sample_k)
    res_by_op: Dict[str, Reservoir] = {
        "put": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF01),
        "get": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF02),
        "del": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF03),
    }

    last_probe_hist: List[List[int]] = []
    last_key_heatmap: Dict[str, Any] = {
        "rows": 0,
        "cols": 0,
        "matrix": [],
        "max": 0,
        "total": 0,
        "slot_span": 1,
        "original_slots": 0,
    }

    def percentile_packet(res: Reservoir) -> Dict[str, float]:
        return res.percentiles([0.50, 0.90, 0.99])

    def reservoir_summary(res: Reservoir) -> Optional[Dict[str, float]]:
        if not res.buf:
            return None
        return {"count": float(len(res.buf)), "sum": float(sum(res.buf))}

    def reservoir_histogram(res: Reservoir) -> List[Tuple[float, int]]:
        if not res.buf:
            return []
        data = sorted(res.buf)
        buckets: List[Tuple[float, int]] = []
        idx = 0
        total = len(data)
        for bound in latency_bucket_bounds:
            while idx < total and data[idx] <= bound:
                idx += 1
            buckets.append((bound, idx))
        return buckets

    def emit_tick(force_sample: bool = False) -> None:
        nonlocal last_probe_hist, last_key_heatmap
        sample_metrics(m, metrics)
        if force_sample:
            last_probe_hist = collect_probe_histogram(m)
            last_key_heatmap = collect_key_heatmap(m)
        reservoir_map: Dict[str, Reservoir] = {"overall": overall_res}
        reservoir_map.update(res_by_op)
        latency_summary_stats: Dict[str, Dict[str, float]] = {}
        latency_histograms: Dict[str, List[Tuple[float, int]]] = {}
        for label, res in reservoir_map.items():
            summary = reservoir_summary(res)
            if summary:
                latency_summary_stats[label] = summary
            hist = reservoir_histogram(res)
            if hist:
                latency_histograms[label] = hist

        tick = {
            "schema": "metrics.v1",
            "t": clock(),
            "backend": metrics.backend_name,
            "ops": int(metrics.ops_total),
            "ops_by_type": {
                "put": int(metrics.puts_total),
                "get": int(metrics.gets_total),
                "del": int(metrics.dels_total),
            },
            "migrations": int(metrics.migrations_total),
            "compactions": int(metrics.compactions_total),
            "load_factor": float(metrics.load_factor),
            "max_group_len": float(metrics.max_group_len),
            "avg_probe_estimate": float(metrics.avg_probe_estimate),
            "tombstone_ratio": float(metrics.tombstone_ratio),
            "probe_hist": last_probe_hist,
            "key_heatmap": last_key_heatmap,
            "latency_ms": {
                "overall": percentile_packet(overall_res),
                "put": percentile_packet(res_by_op["put"]),
                "get": percentile_packet(res_by_op["get"]),
                "del": percentile_packet(res_by_op["del"]),
            },
        }
        tick["latency_hist_ms"] = {
            op: [
                {"le": _format_bucket_label(bound), "count": count}
                for bound, count in hist
            ]
            for op, hist in latency_histograms.items()
        }
        tick["latency_hist_preset"] = latency_hist_preset
        tick["events"] = list(events)
        latency_ms_dict = cast(Dict[str, Dict[str, float]], tick["latency_ms"])
        overall_ms = latency_ms_dict.get("overall", {})
        latency_ns = {q: int(max(value, 0.0) * 1_000_000) for q, value in overall_ms.items()}
        tick["latency_ns"] = latency_ns
        alerts, alert_flags = watchdog.evaluate(tick)
        tick["alerts"] = alerts
        metrics.alert_flags = alert_flags
        metrics.active_alerts = alerts
        metrics.latency_summary_stats = latency_summary_stats
        metrics.latency_histograms = latency_histograms
        metrics.key_heatmap = last_key_heatmap
        metrics.latest_tick = tick
        history_buffer.append(tick)
        if metrics_file is None:
            return
        if metrics_max_ticks and metrics_max_ticks > 0:
            metrics_file.seek(0)
            metrics_file.truncate(0)
            for item in history_buffer:
                metrics_file.write(json.dumps(item) + "\n")
        else:
            metrics_file.write(json.dumps(tick) + "\n")
        metrics_file.flush()

    emit_tick(force_sample=True)
    last_compact = start

    try:
        for op_idx, (op, k, v) in enumerate(load_ops(), 1):
            if want_latency and (op_idx % latency_sample_every == 0):
                t0 = time.perf_counter()
                run_op(m, op, k, v, metrics=metrics)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                overall_res.offer(dt_ms)
                if op in res_by_op:
                    res_by_op[op].offer(dt_ms)
            else:
                run_op(m, op, k, v, metrics=metrics)

            metrics.ops_total += 1
            if metrics.ops_total % 1024 == 0:
                emit_tick(force_sample=True)

            if compact_interval is not None:
                now = time.perf_counter()
                if now - last_compact >= compact_interval:
                    last_compact = now
                    sample_metrics(m, metrics)
                    backend_name = metrics.backend_name
                    if isinstance(m, HybridAdaptiveHashMap):
                        if m._migrating_to is None and isinstance(m._backend, RobinHoodMap):
                            logger.info("Proactive compaction tick (interval=%.2fs)", compact_interval)
                            m._backend.compact()
                            sink.inc_compactions()
                            sink.record_event("compaction", {"backend": backend_name, "source": "proactive"})
                    elif isinstance(m, RobinHoodMap):
                        logger.info("Proactive compaction tick (interval=%.2fs)", compact_interval)
                        m.compact()
                        sink.inc_compactions()
                        sink.record_event("compaction", {"backend": backend_name, "source": "proactive"})

        emit_tick(force_sample=True)
        elapsed = time.perf_counter() - start
        logger.info("run-csv finished in %.6f s, backend=%s", elapsed, metrics.backend_name)

        summary = {
            "elapsed_seconds": elapsed,
            "total_ops": metrics.ops_total,
            "ops_per_second": (metrics.ops_total / elapsed) if elapsed > 0 else None,
            "final_backend": metrics.backend_name,
            "migrations_triggered": metrics.migrations_total,
            "compactions_triggered": metrics.compactions_total,
            "latency_ms": {
                "overall": percentile_packet(overall_res),
                "put": percentile_packet(res_by_op["put"]),
                "get": percentile_packet(res_by_op["get"]),
                "del": percentile_packet(res_by_op["del"]),
            },
            "latency_sample": {
                "reservoir_k_overall": overall_res.k,
                "reservoir_k_each": res_by_op["put"].k,
                "seen_overall": overall_res.n,
                "every_n_ops": latency_sample_every,
            },
            "latency_histogram_preset": latency_hist_preset,
        }

        run_result.update(
            {
                "status": "completed",
                "elapsed_seconds": elapsed,
                "total_ops": int(metrics.ops_total),
                "ops_per_second": summary["ops_per_second"],
                "final_backend": metrics.backend_name,
                "migrations_triggered": int(metrics.migrations_total),
                "compactions_triggered": int(metrics.compactions_total),
                "alerts": metrics.active_alerts,
                "events": list(events),
                "latency_histogram_preset": latency_hist_preset,
                "summary": summary,
            }
        )

        if metrics_path is not None:
            run_result["metrics_file"] = str(metrics_path)

        if json_summary_out:
            with open(json_summary_out, "w") as jf:
                json.dump(summary, jf, indent=2)
            logger.info("Wrote JSON summary: %s", json_summary_out)

        if snapshot_out:
            if isinstance(m, (TwoLevelChainingMap, RobinHoodMap, HybridAdaptiveHashMap)):
                m.save(snapshot_out, compress=compress_out)
            else:
                _save_snapshot_any(m, snapshot_out, compress_out)
            logger.info("Wrote snapshot to %s (compress=%s)", snapshot_out, compress_out)
            run_result["snapshot_written"] = snapshot_out

    finally:
        if server is not None:
            try:
                server.shutdown()
            finally:
                server.server_close()
        if metrics_file is not None:
            metrics_file.close()

    return run_result

# --------------------------------------------------------------------
# Verification (with optional repair)
# --------------------------------------------------------------------
def _verify_chaining(m: TwoLevelChainingMap, verbose: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    total = 0
    for groups in m._buckets:
        for grp in groups:
            total += len(grp)
    ok = (total == m._size)
    if not ok:
        msgs.append(f"Size mismatch: size={m._size}, summed={total}")
    if verbose:
        msgs.append(f"Buckets={m.M}, Groups/Bucket={m.G}, Size={m._size}, MaxGroupLen={m.max_group_len()}")
    return ok, msgs

def _verify_robinhood(m: RobinHoodMap, verbose: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    bound_ok = (m._size + m._tombstones) <= m._cap
    if not bound_ok:
        msgs.append(f"Bound violated: size+tombstones={m._size + m._tombstones} > cap={m._cap}")
    count = sum(1 for _ in m.items())
    size_ok = (count == m._size)
    if not size_ok:
        msgs.append(f"Item iteration count={count} != size={m._size}")
    if verbose:
        msgs.append(f"Cap={m._cap}, Size={m._size}, Tombstones={m._tombstones}, "
                    f"LF={m.load_factor():.3f}, TZ={m.tombstone_ratio():.3f}")
    return (bound_ok and size_ok), msgs

def _verify_hybrid(m: HybridAdaptiveHashMap, verbose: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    while m._migrating_to:
        m._drain_migration()
    ok = True
    inner = getattr(m, "_backend", None)
    if isinstance(inner, TwoLevelChainingMap):
        ok2, msg2 = _verify_chaining(inner, verbose)
        ok = ok and ok2
        msgs += [f"[backend=chaining] {s}" for s in msg2]
    elif isinstance(inner, RobinHoodMap):
        ok2, msg2 = _verify_robinhood(inner, verbose)
        ok = ok and ok2
        msgs += [f"[backend=robinhood] {s}" for s in msg2]
    else:
        ok = False
        msgs.append("Unknown inner backend type")
    if verbose:
        msgs.append(f"Hybrid name={m.backend_name()}, size={len(m)}")
    return ok, msgs

def verify_snapshot(path: str, verbose: bool = False,
                    repair: bool = False, repair_out: Optional[str] = None) -> int:
    """
    Verify invariants of a snapshot. If --repair is passed and the map is a RobinHoodMap
    (or Hybrid with RH active), compacts to purge tombstones / fix counters and writes
    to --out if provided (else in-place rewrite).
    """
    try:
        with _open_for_read(path) as f:
            snap = pickle.load(f)
    except Exception as e:
        print(f"ERROR: failed to load snapshot: {e}")
        return 1

    def write_snapshot(obj: Any, out_path: str) -> None:
        with _open_for_write(out_path, compress=out_path.endswith(".gz")) as wf:
            pickle.dump(obj, wf)

    ok = False
    messages: List[str] = []

    # Dispatch verify
    if isinstance(snap, TwoLevelChainingMap):
        ok, messages = _verify_chaining(snap, verbose)
        target_for_repair = None
    elif isinstance(snap, RobinHoodMap):
        ok, messages = _verify_robinhood(snap, verbose)
        target_for_repair = snap
    elif isinstance(snap, HybridAdaptiveHashMap):
        ok, messages = _verify_hybrid(snap, verbose)
        target_for_repair = None
        inner = getattr(snap, "_backend", None)
        if isinstance(inner, RobinHoodMap):
            target_for_repair = inner
    elif isinstance(snap, dict) and "backend" in snap:
        try:
            m = HybridAdaptiveHashMap.load(path)
            ok, messages = _verify_hybrid(m, verbose)
            inner = getattr(m, "_backend", None)
            target_for_repair = inner if isinstance(inner, RobinHoodMap) else None
            snap = m
        except Exception as e:
            print(f"ERROR: invalid hybrid state: {e}")
            return 1
    else:
        print("ERROR: unsupported snapshot object")
        return 1

    # Report
    if ok:
        print("OK: snapshot verified")
    else:
        print("FAIL: snapshot invariants violated")
    for msg in messages:
        print(msg)

    # Optional repair (safe compaction only)
    if repair and target_for_repair is not None:
        print("Attempting safe repair (compaction of RobinHoodMap)...")
        try:
            target_for_repair.compact()
            out_path = repair_out or path
            if isinstance(snap, (TwoLevelChainingMap, RobinHoodMap)):
                write_snapshot(snap, out_path)
            else:
                snap.save(out_path, compress=out_path.endswith(".gz"))
            print(f"Repair complete. Wrote repaired snapshot to: {out_path}")
            # Post-repair check
            if isinstance(snap, TwoLevelChainingMap):
                ok2, _ = _verify_chaining(snap, False)
            elif isinstance(snap, RobinHoodMap):
                ok2, _ = _verify_robinhood(snap, False)
            else:
                ok2, _ = _verify_hybrid(snap, False)
            print("Post-repair verification:", "OK" if ok2 else "FAILED")
            ok = ok and ok2
        except Exception as e:
            print(f"ERROR: repair failed: {e}")
            return 1
    elif repair and target_for_repair is None:
        print("NOTICE: --repair requested but snapshot/backend is not a RobinHoodMap; no safe repair applicable.")

    return 0 if ok else 1

# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------
def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="HashMap CLI with multi-backend, adaptive mode, generator, profiler, metrics, snapshots, verification (with repair), and CI summaries.")
    p.add_argument("--mode", default="adaptive",
                   choices=["fast-insert", "fast-lookup", "memory-tight", "adaptive"],
                   help="Select backend when not loading a snapshot.")
    p.add_argument("--log-json", action="store_true", help="Emit logs in JSON format")
    p.add_argument("--log-file", default=None,
                   help="Optional log file path (rotates at 5MB, keeps 5 backups by default)")
    p.add_argument("--log-max-bytes", type=int, default=DEFAULT_LOG_MAX_BYTES,
                   help="Max bytes per log file before rotation (default: %(default)s)")
    p.add_argument("--log-backup-count", type=int, default=DEFAULT_LOG_BACKUP_COUNT,
                   help="Number of rotated log files to keep (default: %(default)s)")
    p.add_argument("--json", action="store_true",
                   help="Emit machine-readable success output to stdout")
    p.add_argument("--config", default=None,
                   help="Path to TOML config file (overrides defaults and env overrides)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Simple ops
    p_put = sub.add_parser("put")
    p_put.add_argument("key")
    p_put.add_argument("value")
    p_get = sub.add_parser("get")
    p_get.add_argument("key")
    p_del = sub.add_parser("del")
    p_del.add_argument("key")
    sub.add_parser("items")

    # Profile
    p_prof = sub.add_parser("profile", help="Profile a CSV workload and print the recommended mode.")
    p_prof.add_argument("--csv", required=True)
    p_prof.add_argument("--then", nargs=argparse.REMAINDER, help="After profiling, run one command with the picked mode.")

    # Generator
    p_gen = sub.add_parser("generate-csv", help="Generate a synthetic workload CSV.")
    p_gen.add_argument("--outfile", required=True)
    p_gen.add_argument("--ops", type=int, default=100000)
    p_gen.add_argument("--read-ratio", type=float, default=0.8)
    p_gen.add_argument("--key-skew", type=float, default=0.0)
    p_gen.add_argument("--key-space", type=int, default=10000)
    p_gen.add_argument("--seed", type=int, default=1337)
    p_gen.add_argument("--del-ratio", type=float, default=0.2)
    p_gen.add_argument("--adversarial-ratio", type=float, default=0.0)
    p_gen.add_argument("--adversarial-lowbits", type=int, default=6)

    # Runner
    p_run = sub.add_parser("run-csv", help="Replay a CSV workload (metrics, snapshots, compaction, JSON summary).")
    p_run.add_argument("--csv", required=True)
    p_run.add_argument("--metrics-port", type=int, default=None)
    p_run.add_argument("--metrics-out-dir", type=str, default=None,
                       help="Directory for metrics.ndjson (schema=metrics.v1)")
    p_run.add_argument("--dry-run", action="store_true",
                       help="Validate the CSV workload and exit without executing it")
    p_run.add_argument("--csv-max-rows", type=int, default=DEFAULT_CSV_MAX_ROWS,
                       help="Abort if CSV rows exceed this count (0 disables check)")
    p_run.add_argument("--csv-max-bytes", type=int, default=DEFAULT_CSV_MAX_BYTES,
                       help="Abort if CSV file size exceeds this many bytes (0 disables check)")
    p_run.add_argument("--metrics-max-ticks", type=int, default=None,
                       help="Optional retention limit for metrics.ndjson (keep last N ticks)")
    p_run.add_argument("--snapshot-in", type=str, default=None, help="Load initial snapshot (.gz auto-detected)")
    p_run.add_argument("--snapshot-out", type=str, default=None, help="Write snapshot after run")
    p_run.add_argument("--compress", action="store_true", help="Gzip-compress snapshot writes or use .gz suffix")
    p_run.add_argument("--compact-interval", type=float, default=None, help="Seconds between proactive compactions")
    p_run.add_argument("--json-summary-out", type=str, default=None, help="Write final run stats to JSON for CI")
    p_run.add_argument("--latency-sample-k", type=int, default=1000, help="Reservoir size for latency sampling")
    p_run.add_argument("--latency-sample-every", type=int, default=128, help="Sample every Nth operation")
    p_run.add_argument(
        "--latency-buckets",
        choices=sorted(LATENCY_BUCKET_PRESETS_MS.keys()),
        default="default",
        help="Latency histogram bucket preset (default: %(default)s)",
    )

    # Config wizard
    p_wizard = sub.add_parser("config-wizard", help="Interactively generate a TOML config file.")
    p_wizard.add_argument(
        "--outfile",
        default="config.generated.toml",
        help="Where to write the generated config (default: %(default)s)",
    )

    sub.add_parser("mission-control", help="Launch the Mission Control desktop UI (PyQt6).")

    # Serve (sticky metrics/dashboard)
    p_serve = sub.add_parser("serve", help="Serve the dashboard/metrics API without running a workload.")
    p_serve.add_argument("--port", type=int, default=9090, help="Port for the metrics server (default: %(default)s)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host/interface to bind (default: %(default)s)")
    p_serve.add_argument("--source", default=None, help="Optional metrics NDJSON file to load")
    p_serve.add_argument("--follow", action="store_true", help="Tail the metrics source for new ticks")
    p_serve.add_argument("--history-limit", type=int, default=360, help="History buffer length for dashboard plots")
    p_serve.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between tail polls when following")

    # Offline compaction
    p_comp = sub.add_parser("compact-snapshot", help="Compact a RobinHoodMap snapshot offline.")
    p_comp.add_argument("--in", dest="infile", required=True)
    p_comp.add_argument("--out", dest="outfile", required=True)
    p_comp.add_argument("--compress", action="store_true")

    # Verification
    p_ver = sub.add_parser("verify-snapshot", help="Verify invariants of a snapshot; optional safe repair (RobinHoodMap).")
    p_ver.add_argument("--in", dest="infile", required=True)
    p_ver.add_argument("--verbose", action="store_true")
    p_ver.add_argument("--repair", action="store_true", help="Attempt safe repair (RobinHood compaction).")
    p_ver.add_argument("--out", dest="outfile", default=None, help="Write repaired snapshot to this path (default: overwrite input)")

    args = p.parse_args(argv)

    global OUTPUT_JSON
    OUTPUT_JSON = bool(args.json)

    configure_logging(
        args.log_json,
        args.log_file,
        max_bytes=args.log_max_bytes,
        backup_count=args.log_backup_count,
    )

    cfg_path = args.config or os.getenv("ADHASH_CONFIG")
    cfg = load_app_config(cfg_path)
    set_app_config(cfg)
    if cfg_path:
        logger.info("Loaded config from %s", cfg_path)

    handlers: Dict[str, Callable[[argparse.Namespace], int]] = {
        "put": _cmd_put,
        "get": _cmd_get,
        "del": _cmd_del,
        "items": _cmd_items,
        "profile": _cmd_profile,
        "generate-csv": _cmd_generate,
        "run-csv": _cmd_run_csv,
        "config-wizard": _cmd_config_wizard,
        "mission-control": _cmd_mission_control,
        "serve": _cmd_serve,
        "compact-snapshot": _cmd_compact_snapshot,
        "verify-snapshot": _cmd_verify_snapshot,
    }

    handler = handlers.get(args.cmd)
    if handler is None:
        raise PolicyError(f"Unknown command {args.cmd}")
    return handler(args)

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(2)
