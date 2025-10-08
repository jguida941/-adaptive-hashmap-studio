from __future__ import annotations

import copy
import json
import logging
import math
import os
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from adhash.config import WatchdogPolicy

from .constants import SUMMARY_SCHEMA, TICK_SCHEMA

logger = logging.getLogger("hashmap_cli")

_SUMMARY_QUANTILES = {"p50": "0.5", "p90": "0.9", "p99": "0.99"}


def _coerce_alert_flag(value: Any) -> bool:
    """Normalise watchdog alert flag payloads into booleans."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {
            "true",
            "1",
            "yes",
            "y",
            "on",
        }:  # pragma: no mutate - exhaustive truthy sentinels
            return True
        if lowered in {
            "false",
            "0",
            "no",
            "n",
            "off",
            "",
        }:  # pragma: no mutate - exhaustive falsy sentinels
            return False
        return bool(lowered)
    if isinstance(value, (int, float)):
        return bool(value)
    return bool(value)


def resolve_ema_alpha(default: float = 0.25) -> float:
    """Resolve the EMA smoothing factor from environment with validation."""

    raw = os.getenv(
        "ADHASH_OPS_ALPHA", str(default)
    )  # pragma: no mutate - default ensures castable string
    try:
        alpha = float(raw)
    except (TypeError, ValueError):
        alpha = default
    return max(0.0, min(1.0, alpha))


def format_bucket_label(bound: float) -> str:
    return "+Inf" if math.isinf(bound) else f"{bound:.6f}"


class Metrics:
    def __init__(self) -> None:
        self.ops_total = 0
        self.puts_total = 0
        self.gets_total = 0
        self.dels_total = 0
        self.migrations_total = 0
        self.compactions_total = 0
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
        self._ema_alpha = resolve_ema_alpha()
        self._ema_ops = 0.0
        self._ops_prev: Optional[float] = None
        self._t_prev: Optional[float] = None
        self._last_instant: Optional[float] = None

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
        latency_ms = latest.get(
            "latency_ms", {}
        )  # pragma: no mutate - empty dict keeps downstream loops safe
        if latency_ms:
            lines.append(
                "# HELP hashmap_latency_ms Latency percentiles (ms) by operation and quantile"
            )
            lines.append("# TYPE hashmap_latency_ms gauge")
            for op, packet in latency_ms.items():
                for q, value in packet.items():
                    lines.append(f'hashmap_latency_ms{{op="{op}",quantile="{q}"}} {value:.6f}')

            summary_ops = {
                op: stats
                for op, stats in self.latency_summary_stats.items()
                if stats.get("count", 0)
            }  # pragma: no mutate - zero-count summaries should be filtered
            if summary_ops:
                lines.append(
                    "# HELP hashmap_latency_ms_summary Sampled latency summaries (ms) per operation"
                )
                lines.append("# TYPE hashmap_latency_ms_summary summary")
                for op in sorted(summary_ops):
                    packet = latency_ms.get(
                        op, {}
                    )  # pragma: no mutate - default keeps missing ops safe
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
            }  # pragma: no mutate - empty buckets suppress histogram output
            if hist_ops:
                lines.append(
                    "# HELP hashmap_latency_ms_hist Sampled latency histogram (ms) per operation"
                )
                lines.append("# TYPE hashmap_latency_ms_hist histogram")
                for op in sorted(hist_ops):
                    buckets = hist_ops[op]
                    stats = self.latency_summary_stats.get(op, {})
                    for upper, cumulative in buckets:
                        label = format_bucket_label(upper)
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
            lines.append(
                "# HELP hashmap_probe_length_count Probe length histogram (count per distance)"
            )
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

    def update_rates(self, tick: Dict[str, Any]) -> None:
        ops_raw = tick.get("ops")
        t_raw = tick.get("t")
        ops = float(ops_raw) if isinstance(ops_raw, (int, float)) else None
        t_now = float(t_raw) if isinstance(t_raw, (int, float)) else None
        wall_now = time.time()
        if t_now is None:
            t_now = wall_now

        inst: Optional[float] = None
        if ops is not None and self._ops_prev is not None and self._t_prev is not None:
            dt = t_now - self._t_prev
            dt = max(1e-3, min(10.0, dt))
            if dt > 0:
                inst = max(0.0, (ops - self._ops_prev) / dt)

        if inst is None:
            for key in ("ops_per_second", "throughput", "ops_per_second_instant"):
                inst_raw = tick.get(key)
                if isinstance(inst_raw, (int, float)):
                    inst = float(inst_raw)
                    break

        if inst is not None:
            if self._t_prev is None or self._ops_prev is None:
                self._ema_ops = inst
            else:
                alpha = self._ema_alpha
                self._ema_ops = (alpha * inst) + ((1 - alpha) * self._ema_ops)
            self._last_instant = inst
            tick["ops_per_second_instant"] = inst
            tick["ops_per_second_ema"] = self._ema_ops
        elif self._ema_ops is not None:
            tick.setdefault("ops_per_second_ema", self._ema_ops)

        if ops is not None:
            self._ops_prev = ops
        if t_now is not None:
            self._t_prev = t_now

    def build_summary_payload(self) -> Dict[str, Any]:
        payload = copy.deepcopy(self.latest_tick) if isinstance(self.latest_tick, dict) else {}
        payload["schema"] = SUMMARY_SCHEMA
        payload["generated_at"] = time.time()
        payload.setdefault("backend", self.backend_name)
        payload.setdefault("ops", self.ops_total)
        payload.setdefault("ops_per_second_instant", self._last_instant or 0.0)
        payload.setdefault(
            "ops_per_second", payload.get("ops_per_second_instant", self._last_instant or 0.0)
        )
        payload.setdefault("ops_per_second_ema", self._ema_ops)
        payload["totals"] = {
            "ops": self.ops_total,
            "puts": self.puts_total,
            "gets": self.gets_total,
            "dels": self.dels_total,
            "migrations": self.migrations_total,
            "compactions": self.compactions_total,
        }
        payload["backend_state"] = {
            "name": self.backend_name,
            "load_factor": self.load_factor,
            "max_group_len": self.max_group_len,
            "avg_probe_estimate": self.avg_probe_estimate,
            "tombstone_ratio": self.tombstone_ratio,
        }
        payload["alerts"] = copy.deepcopy(self.active_alerts)
        payload["alert_flags"] = dict(self.alert_flags)
        return payload


def apply_tick_to_metrics(metrics: Metrics, tick: Dict[str, Any]) -> None:
    """Apply a metrics tick dictionary to the in-memory Metrics object."""

    tick = copy.deepcopy(tick)
    metrics.update_rates(tick)

    ops_by_type = tick.get("ops_by_type", {})
    if isinstance(ops_by_type, dict):
        metrics.puts_total = int(ops_by_type.get("put", metrics.puts_total))
        metrics.gets_total = int(ops_by_type.get("get", metrics.gets_total))
        metrics.dels_total = int(ops_by_type.get("del", metrics.dels_total))
    metrics.ops_total = int(tick.get("ops", metrics.ops_total))
    metrics.migrations_total = int(tick.get("migrations", metrics.migrations_total))
    metrics.compactions_total = int(tick.get("compactions", metrics.compactions_total))
    metrics.load_factor = float(tick.get("load_factor", metrics.load_factor))
    metrics.max_group_len = float(tick.get("max_group_len", metrics.max_group_len))
    metrics.avg_probe_estimate = float(tick.get("avg_probe_estimate", metrics.avg_probe_estimate))
    metrics.tombstone_ratio = float(tick.get("tombstone_ratio", metrics.tombstone_ratio))
    metrics.backend_name = str(tick.get("backend", metrics.backend_name))

    alerts = tick.get("alerts")
    if isinstance(alerts, list):
        metrics.active_alerts = [item for item in alerts if isinstance(item, dict)]
    alert_flags = tick.get("alert_flags")
    if isinstance(alert_flags, dict):
        metrics.alert_flags = {str(k): _coerce_alert_flag(v) for k, v in alert_flags.items()}

    latency_summary_stats = tick.get("latency_summary_stats")
    if isinstance(latency_summary_stats, dict):
        parsed_summary: Dict[str, Dict[str, float]] = {}
        for key, item in latency_summary_stats.items():
            if not isinstance(item, dict):
                continue
            parsed_summary[str(key)] = {
                str(k): float(v) for k, v in item.items() if isinstance(v, (int, float))
            }
        metrics.latency_summary_stats = parsed_summary

    latency_histograms = tick.get("latency_histograms")
    if isinstance(latency_histograms, dict):
        parsed_hist: Dict[str, List[Tuple[float, int]]] = {}
        for label, buckets in latency_histograms.items():
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
                if math.isnan(upper):
                    continue
                parsed.append((upper, count))
            if parsed:
                parsed_hist[str(label)] = parsed
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


def parse_tick_line(line: str) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        logger.debug("Ignored invalid metrics line: %s", line.strip())
        return None
    if not isinstance(payload, dict):
        return None
    schema = payload.get("schema")
    if schema not in (None, TICK_SCHEMA):
        logger.debug("Skipping metrics tick with schema=%s", schema)
        return None
    return payload


def stream_metrics_file(
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
                    tick = parse_tick_line(line)
                    if tick is not None:
                        callback(tick)
        except FileNotFoundError:
            if not follow:
                logger.error("Metrics source not found: %s", path)
                return
            if not waiting_logged:
                logger.info("Waiting for metrics source to appear: %s", path)
                waiting_logged = True
            time.sleep(poll_interval)


class ThresholdWatchdog:
    """Evaluate metrics against configured guardrails and emit alerts."""

    def __init__(self, policy: WatchdogPolicy) -> None:
        self.policy = policy
        self._state: Dict[str, bool] = {}

    def evaluate(self, tick: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, bool]]:
        if not self.policy.enabled:
            if any(self._state.values()):
                logger.info(
                    "Watchdog disabled; clearing %d active alerts",
                    sum(1 for active in self._state.values() if active),
                )
            self._state.clear()
            return [], {}

        backend = str(tick.get("backend", "unknown"))
        alerts: List[Dict[str, Any]] = []
        flags: Dict[str, bool] = {}

        checks = [
            (
                "load_factor",
                tick.get("load_factor"),
                self.policy.load_factor_warn,
                "Load factor guardrail exceeded",
            ),
            (
                "avg_probe_estimate",
                tick.get("avg_probe_estimate"),
                self.policy.avg_probe_warn,
                "Probe length guardrail exceeded",
            ),
            (
                "tombstone_ratio",
                tick.get("tombstone_ratio"),
                self.policy.tombstone_ratio_warn,
                "Tombstone ratio guardrail exceeded",
            ),
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


__all__ = [
    "Metrics",
    "ThresholdWatchdog",
    "apply_tick_to_metrics",
    "parse_tick_line",
    "resolve_ema_alpha",
    "stream_metrics_file",
    "format_bucket_label",
]
