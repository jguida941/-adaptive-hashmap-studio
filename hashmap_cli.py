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
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, cast

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

try:  # pragma: no cover - executed only during development
    from adhash.config import AppConfig, load_app_config  # noqa: F401
    from adhash.config_toolkit import (
        clone_config,
        format_app_config_to_toml,
        load_config_document,
        load_preset,
        prompt_for_config,
        resolve_presets_dir,
        save_preset,
    )
    from adhash.contracts.error import (
        BadInputError,
        InvariantError,
        IOErrorEnvelope,
        PolicyError,
        guard_cli,
    )
    from adhash.io.snapshot import (
        atomic_map_save,
        load_snapshot_any,
        save_snapshot_any,
    )
    from adhash.metrics import (  # noqa: F401
        Metrics,
        ThresholdWatchdog,
        apply_tick_to_metrics,
        format_bucket_label,
        start_metrics_server,
        stream_metrics_file,
        TICK_SCHEMA,
    )
    from adhash.core.latency import (
        LATENCY_BUCKET_PRESETS_MS,
        Reservoir,
        resolve_latency_bucket_bounds,
    )
    from adhash.core.maps import (
        AdaptiveConfig,
        HybridAdaptiveHashMap,
        MetricsSink,
        RobinHoodMap,
        TwoLevelChainingMap,
        collect_key_heatmap,
        collect_probe_histogram,
        reattach_runtime_callbacks,
        sample_metrics,
    )
    from adhash.cli.commands import CLIContext, register_subcommands
    from adhash.workloads import analyze_workload_csv
except ModuleNotFoundError:  # pragma: no cover - fallback when running from repo root
    if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))
    from adhash.config import AppConfig, load_app_config  # noqa: F401
    from adhash.config_toolkit import (
        clone_config,
        format_app_config_to_toml,
        load_config_document,
        load_preset,
        prompt_for_config,
        resolve_presets_dir,
        save_preset,
    )
    from adhash.contracts.error import (
        BadInputError,
        InvariantError,
        IOErrorEnvelope,
        PolicyError,
        guard_cli,
    )
    from adhash.io.snapshot import (
        atomic_map_save,
        load_snapshot_any,
        save_snapshot_any,
    )
    from adhash.core.latency import (
        LATENCY_BUCKET_PRESETS_MS,
        Reservoir,
        resolve_latency_bucket_bounds,
    )
    from adhash.core.maps import (
        AdaptiveConfig,
        HybridAdaptiveHashMap,
        MetricsSink,
        RobinHoodMap,
        TwoLevelChainingMap,
        collect_key_heatmap,
        collect_probe_histogram,
        reattach_runtime_callbacks,
        sample_metrics,
    )

    from adhash.cli.commands import CLIContext, register_subcommands
    from adhash.workloads import analyze_workload_csv


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

def _write_config_file(cfg: AppConfig, outfile: str | Path) -> Path:
    out_path = Path(outfile).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(format_app_config_to_toml(cfg), encoding="utf-8")
    return out_path


def run_config_wizard(
    outfile: str,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> Path:
    """Interactive CLI wizard that writes a TOML config file."""

    cfg = prompt_for_config(AppConfig(), input_fn=input_fn, print_fn=print_fn)
    out_path = _write_config_file(cfg, outfile)
    print_fn("")
    print_fn(f"Configuration written to {out_path}")
    print_fn("Pass `--config` or set ADHASH_CONFIG to use it.")
    return out_path


def run_config_editor(
    infile: Optional[str],
    outfile: Optional[str],
    *,
    apply_preset: Optional[str] = None,
    save_preset_name: Optional[str] = None,
    presets_dir: Optional[str] = None,
    force: bool = False,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Interactive config editor that supports presets and existing files."""

    preset_dir_path: Optional[Path] = None
    if apply_preset or save_preset_name:
        preset_dir_path = resolve_presets_dir(presets_dir)

    base_source = "defaults"
    base_cfg: AppConfig

    if apply_preset:
        assert preset_dir_path is not None
        base_cfg = clone_config(load_preset(apply_preset, preset_dir_path))
        base_source = f"preset:{apply_preset}"
        print_fn(f"Loaded preset '{apply_preset}' from {preset_dir_path}")
    else:
        base_cfg = AppConfig()
        if infile:
            in_path = Path(infile).expanduser().resolve()
            if in_path.exists():
                base_cfg = clone_config(load_config_document(in_path))
                base_source = str(in_path)
                print_fn(f"Loaded config from {in_path}")
            else:
                print_fn(f"No config at {in_path}; starting from defaults.")

    cfg = prompt_for_config(base_cfg, input_fn=input_fn, print_fn=print_fn)

    target = outfile or infile or "config.toml"
    out_path = _write_config_file(cfg, target)
    print_fn("")
    print_fn(f"Configuration written to {out_path}")

    preset_path: Optional[Path] = None
    if save_preset_name:
        if preset_dir_path is None:
            preset_dir_path = resolve_presets_dir(presets_dir)
        preset_path = save_preset(cfg, save_preset_name, preset_dir_path, overwrite=force)
        print_fn(f"Preset saved to {preset_path}")

    result: Dict[str, Any] = {"outfile": str(out_path), "base": base_source}
    if preset_path is not None:
        result["preset"] = str(preset_path)
    if preset_dir_path is not None:
        result["presets_dir"] = str(preset_dir_path)
    if apply_preset:
        result["apply_preset"] = apply_preset
    if save_preset_name:
        result["save_preset"] = save_preset_name
    return result




def build_map(
    mode: str,
    metrics: Optional[Metrics] = None,
    *,
    sink: Optional[MetricsSink] = None,
) -> Any:
    policy = APP_CONFIG.adaptive
    sink = sink or MetricsSink(metrics)

    def make_adaptive() -> HybridAdaptiveHashMap:
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
        chaining = TwoLevelChainingMap(initial_buckets=policy.initial_buckets,
                                       groups_per_bucket=policy.groups_per_bucket)
        sink.attach(chaining)
        return chaining
    if mode in ("fast-lookup", "memory-tight"):
        robin = RobinHoodMap(initial_capacity=policy.initial_capacity_rh)
        sink.attach(robin)
        return robin
    if mode == "adaptive":
        return make_adaptive()
    raise ValueError(f"unknown mode: {mode}")


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


def analyze_workload(path: str, top_keys: int, max_tracked_keys: int):
    return analyze_workload_csv(path, top_keys=top_keys, max_tracked_keys=max_tracked_keys)

# --------------------------------------------------------------------
# Runner with proactive compaction, JSON summary (+ percentiles), snapshots
# --------------------------------------------------------------------
def _parse_port(raw: str) -> int:
    port = int(raw)
    if port == 0:
        return 0
    if not (1 <= port <= 65_535):
        raise ValueError("port must be between 0 and 65535")
    return port


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
            csv_max_bytes: int = DEFAULT_CSV_MAX_BYTES,
            metrics_host: Optional[str] = None,
            *,
            capture_history: bool = False) -> Dict[str, Any]:
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

    if metrics_port is None:
        env_port = os.getenv("ADHASH_METRICS_PORT")
        if env_port:
            try:
                env_value = env_port.strip()
                if env_value.lower() == "auto":
                    metrics_port = 0
                else:
                    metrics_port = _parse_port(env_value)
            except ValueError as exc:
                raise BadInputError(
                    f"Invalid ADHASH_METRICS_PORT '{env_port}'",
                    hint="Set ADHASH_METRICS_PORT to an integer port or 'auto'.",
                ) from exc

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
    server = None
    stop_server = None
    bind_host = metrics_host or os.getenv("ADHASH_METRICS_HOST") or "127.0.0.1"
    if metrics_port is not None:
        server, stop_server = start_metrics_server(metrics, metrics_port, host=bind_host)
        actual_port = getattr(server, "server_port", metrics_port)
        run_result["metrics_port"] = actual_port
        run_result["metrics_host"] = bind_host

    metrics_file = None
    metrics_path: Optional[Path] = None
    if metrics_out_dir:
        out_dir = Path(metrics_out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_mode = "w+" if metrics_max_ticks and metrics_max_ticks > 0 else "a"
        metrics_path = out_dir / "metrics.ndjson"
        metrics_file = metrics_path.open(file_mode, encoding="utf-8")

    events: List[Dict[str, Any]] = []
    idle_grace = 5.0
    idle_active = False
    resume_pending = False
    last_ops_change = 0.0

    start = time.perf_counter()

    def clock() -> float:
        return time.perf_counter() - start

    last_ops_change = clock()
    sink = MetricsSink(metrics, events, clock)
    watchdog = ThresholdWatchdog(APP_CONFIG.watchdog)

    if snapshot_in:
        try:
            snap = load_snapshot_any(snapshot_in)
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

    reattach_runtime_callbacks(m, sink)

    want_latency = latency_sample_k > 0 and latency_sample_every > 0
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
        nonlocal last_probe_hist, last_key_heatmap, idle_active, resume_pending, last_ops_change
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
            "schema": TICK_SCHEMA,
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
                {"le": format_bucket_label(bound), "count": count}
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

        if resume_pending:
            sink.record_event(
                "resume",
                {"backend": metrics.backend_name, "message": "workload resumed"},
            )
            resume_pending = False

        now = clock()
        idle_elapsed = now - last_ops_change
        is_idle = idle_elapsed >= idle_grace
        if is_idle:
            tick["state"] = "idle"
            tick["idle"] = True
            if not idle_active:
                idle_active = True
                sink.record_event(
                    "idle",
                    {"backend": metrics.backend_name, "message": "workload idle"},
                )
            if history_buffer and len(history_buffer) and history_buffer[-1].get("state") == "idle":
                metrics.latest_tick = history_buffer[-1]
                return
        else:
            idle_active = False
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

    reattach_runtime_callbacks(m, sink)

    sample_metrics(m, metrics)

    sink.record_event("start", {"backend": metrics.backend_name, "message": "workload started"})
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
            last_ops_change = clock()
            if idle_active:
                resume_pending = True
                idle_active = False
                emit_tick(force_sample=True)
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

        sink.record_event(
            "complete",
            {"backend": metrics.backend_name, "message": "workload completed"},
        )
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

        if capture_history:
            run_result["history"] = [dict(item) for item in history_buffer]

        if json_summary_out:
            with open(json_summary_out, "w") as jf:
                json.dump(summary, jf, indent=2)
            logger.info("Wrote JSON summary: %s", json_summary_out)

        if snapshot_out:
            if isinstance(m, (TwoLevelChainingMap, RobinHoodMap, HybridAdaptiveHashMap)):
                atomic_map_save(m, Path(snapshot_out), compress=compress_out)
            else:
                save_snapshot_any(m, snapshot_out, compress_out)
            logger.info("Wrote snapshot to %s (compress=%s)", snapshot_out, compress_out)
            run_result["snapshot_written"] = snapshot_out

    finally:
        if stop_server is not None:
            stop_server()
        if metrics_file is not None:
            metrics_file.close()

    return run_result


def _safe_number(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _delta_packet(baseline: Optional[float], candidate: Optional[float]) -> Dict[str, Optional[float]]:
    delta: Optional[float] = None
    percent: Optional[float] = None
    if baseline is not None and candidate is not None:
        delta = candidate - baseline
        if baseline != 0:
            percent = (delta / baseline) * 100.0
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": delta,
        "percent": percent,
    }


def _latency_deltas(baseline_summary: Dict[str, Any], candidate_summary: Dict[str, Any]) -> Dict[str, Dict[str, Dict[str, Optional[float]]]]:
    output: Dict[str, Dict[str, Dict[str, Optional[float]]]] = {}
    baseline_packet = baseline_summary.get("latency_ms", {}) if isinstance(baseline_summary, dict) else {}
    candidate_packet = candidate_summary.get("latency_ms", {}) if isinstance(candidate_summary, dict) else {}
    for operation in sorted(set(baseline_packet.keys()) | set(candidate_packet.keys())):
        base_series = baseline_packet.get(operation, {}) if isinstance(baseline_packet.get(operation), dict) else {}
        cand_series = candidate_packet.get(operation, {}) if isinstance(candidate_packet.get(operation), dict) else {}
        output[operation] = {}
        for quantile in sorted(set(base_series.keys()) | set(cand_series.keys()) | {"p50", "p90", "p99"}):
            output[operation][quantile] = _delta_packet(
                _safe_number(base_series.get(quantile)),
                _safe_number(cand_series.get(quantile)),
            )
    return output


def _build_timeline(
    baseline_history: List[Dict[str, Any]],
    candidate_history: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    length = min(len(baseline_history), len(candidate_history))
    timeline: List[Dict[str, Any]] = []
    for index in range(length):
        base_tick = baseline_history[index]
        cand_tick = candidate_history[index]
        base_ops = _safe_number(base_tick.get("ops_per_second_ema")) or _safe_number(base_tick.get("ops_per_second_instant"))
        cand_ops = _safe_number(cand_tick.get("ops_per_second_ema")) or _safe_number(cand_tick.get("ops_per_second_instant"))
        base_load = _safe_number(base_tick.get("load_factor"))
        cand_load = _safe_number(cand_tick.get("load_factor"))
        base_probe = _safe_number(base_tick.get("avg_probe_estimate"))
        cand_probe = _safe_number(cand_tick.get("avg_probe_estimate"))
        entry: Dict[str, Any] = {
            "index": index,
            "baseline_t": _safe_number(base_tick.get("t")),
            "candidate_t": _safe_number(cand_tick.get("t")),
            "ops": _delta_packet(base_ops, cand_ops),
            "load_factor": _delta_packet(base_load, cand_load),
            "avg_probe": _delta_packet(base_probe, cand_probe),
        }
        timeline.append(entry)
    return timeline


def run_ab_compare(
    csv: str,
    *,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
    baseline_mode: str = "adaptive",
    candidate_mode: str = "adaptive",
    baseline_config: Optional[str] = None,
    candidate_config: Optional[str] = None,
    latency_sample_k: int = 1000,
    latency_sample_every: int = 128,
    metrics_max_ticks: Optional[int] = None,
    metrics_dir: Optional[str] = None,
    json_out: Optional[str] = None,
    markdown_out: Optional[str] = None,
) -> Dict[str, Any]:
    """Run two ``run-csv`` replays and compute throughput / latency deltas."""

    artifact_dir = Path(metrics_dir).expanduser().resolve() if metrics_dir else None
    if artifact_dir:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    original_cfg = clone_config(APP_CONFIG)

    def _prepare_config(path: Optional[str]) -> AppConfig:
        if path:
            return clone_config(load_app_config(path))
        return clone_config(original_cfg)

    baseline_cfg = _prepare_config(baseline_config)
    candidate_cfg = _prepare_config(candidate_config)

    def _run(tag: str, label: str, mode: str, cfg: AppConfig) -> Dict[str, Any]:
        set_app_config(cfg)
        json_summary_path: Optional[Path] = None
        metrics_out: Optional[str] = None
        if artifact_dir:
            json_summary_path = artifact_dir / f"{tag}_summary.json"
            metrics_out_dir = artifact_dir / tag / "metrics"
            metrics_out_dir.mkdir(parents=True, exist_ok=True)
            metrics_out = metrics_out_dir.as_posix()
        config_raw = baseline_config if tag == "baseline" else candidate_config
        config_resolved = Path(config_raw).expanduser().resolve().as_posix() if config_raw else None
        result = run_csv(
            csv,
            mode,
            json_summary_out=json_summary_path.as_posix() if json_summary_path else None,
            latency_sample_k=latency_sample_k,
            latency_sample_every=latency_sample_every,
            metrics_out_dir=metrics_out,
            metrics_max_ticks=metrics_max_ticks,
            capture_history=True,
        )
        history = result.pop("history", [])
        payload = {
            "label": label,
            "mode": mode,
            "config_path": config_resolved,
            "summary": result.get("summary", {}),
            "events": result.get("events", []),
            "metrics_file": result.get("metrics_file"),
            "history": history,
        }
        return payload

    baseline_payload = _run("baseline", baseline_label, baseline_mode, baseline_cfg)
    candidate_payload = _run("candidate", candidate_label, candidate_mode, candidate_cfg)

    set_app_config(original_cfg)

    baseline_summary = baseline_payload["summary"]
    candidate_summary = candidate_payload["summary"]

    ops_delta = _delta_packet(_safe_number(baseline_summary.get("ops_per_second")), _safe_number(candidate_summary.get("ops_per_second")))
    elapsed_delta = _delta_packet(_safe_number(baseline_summary.get("elapsed_seconds")), _safe_number(candidate_summary.get("elapsed_seconds")))
    migrations_delta = _delta_packet(_safe_number(baseline_summary.get("migrations_triggered")), _safe_number(candidate_summary.get("migrations_triggered")))
    compactions_delta = _delta_packet(_safe_number(baseline_summary.get("compactions_triggered")), _safe_number(candidate_summary.get("compactions_triggered")))

    latency_delta = _latency_deltas(baseline_summary, candidate_summary)
    timeline = _build_timeline(baseline_payload["history"], candidate_payload["history"])

    baseline_payload.pop("history", None)
    candidate_payload.pop("history", None)

    comparison: Dict[str, Any] = {
        "schema": "adhash.compare.v1",
        "metadata": {
            "csv": Path(csv).resolve().as_posix(),
            "generated_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "latency_sample_k": latency_sample_k,
            "latency_sample_every": latency_sample_every,
        },
        "baseline": baseline_payload,
        "candidate": candidate_payload,
        "diff": {
            "ops_per_second": ops_delta,
            "elapsed_seconds": elapsed_delta,
            "migrations": migrations_delta,
            "compactions": compactions_delta,
            "latency_ms": latency_delta,
        },
        "timeline": timeline,
    }

    if json_out:
        json_path = Path(json_out).expanduser().resolve()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
        comparison["metadata"]["comparison_json"] = json_path.as_posix()

    if markdown_out:
        md_path = Path(markdown_out).expanduser().resolve()
        md_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# A/B Comparison — {baseline_label} vs {candidate_label}",
            "",
            f"* CSV: `{Path(csv).resolve().as_posix()}`",
            f"* Generated: {comparison['metadata']['generated_at']}",
            "",
            "| Metric | Baseline | Candidate | Δ | % |",
            "|---|---:|---:|---:|---:|",
            f"| Ops/s | {ops_delta['baseline'] or 0:.2f} | {ops_delta['candidate'] or 0:.2f} | {ops_delta['delta'] or 0:.2f} | {(ops_delta['percent'] or 0):.2f}% |",
            f"| Runtime (s) | {elapsed_delta['baseline'] or 0:.2f} | {elapsed_delta['candidate'] or 0:.2f} | {elapsed_delta['delta'] or 0:.2f} | {(elapsed_delta['percent'] or 0):.2f}% |",
            f"| Migrations | {migrations_delta['baseline'] or 0:.0f} | {migrations_delta['candidate'] or 0:.0f} | {migrations_delta['delta'] or 0:.0f} | {(migrations_delta['percent'] or 0):.2f}% |",
            f"| Compactions | {compactions_delta['baseline'] or 0:.0f} | {compactions_delta['candidate'] or 0:.0f} | {compactions_delta['delta'] or 0:.0f} | {(compactions_delta['percent'] or 0):.2f}% |",
            "",
            "## Latency (overall)",
            "",
            "| Percentile | Baseline (ms) | Candidate (ms) | Δ (ms) | % |",
            "|---|---:|---:|---:|---:|",
        ]
        overall_latency = latency_delta.get("overall", {})
        for quantile in ("p50", "p90", "p99"):
            packet = overall_latency.get(quantile, {})
            lines.append(
                f"| {quantile} | {(packet.get('baseline') or 0):.3f} | {(packet.get('candidate') or 0):.3f} | {(packet.get('delta') or 0):.3f} | {(packet.get('percent') or 0):.2f}% |"
            )
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        comparison["metadata"]["comparison_markdown"] = md_path.as_posix()

    if artifact_dir:
        comparison["metadata"]["artifact_dir"] = artifact_dir.as_posix()

    return comparison

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
        snap = load_snapshot_any(path)
    except Exception as e:
        print(f"ERROR: failed to load snapshot: {e}")
        return 1

    def write_snapshot(obj: Any, out_path: str) -> None:
        save_snapshot_any(obj, out_path, compress=out_path.endswith(".gz"))

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

    ctx = CLIContext(
        emit_success=emit_success,
        build_map=build_map,
        run_op=run_op,
        profile_csv=profile_csv,
        run_csv=run_csv,
        generate_csv=generate_csv,
        run_config_wizard=run_config_wizard,
        run_config_editor=run_config_editor,
        run_ab_compare=run_ab_compare,
        verify_snapshot=verify_snapshot,
        analyze_workload=lambda csv_path, top_keys, max_tracked: analyze_workload(
            csv_path,
            top_keys,
            max_tracked,
        ),
        invoke_main=lambda argv_inner: main(argv_inner),
        logger=logger,
        json_enabled=lambda: OUTPUT_JSON,
        robinhood_cls=RobinHoodMap,
        guard=guard_cli,
        latency_bucket_choices=sorted(LATENCY_BUCKET_PRESETS_MS.keys()),
    )

    handlers = register_subcommands(sub, ctx)

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




    handler = handlers.get(args.cmd)
    if handler is None:
        raise PolicyError(f"Unknown command {args.cmd}")
    return handler(args)

def console_main() -> None:
    """Entry point for console_scripts."""

    try:
        raise SystemExit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        raise SystemExit(2) from e


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(2)
