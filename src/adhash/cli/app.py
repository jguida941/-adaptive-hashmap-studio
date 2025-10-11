#!/usr/bin/env python3
"""
app.py

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
import contextlib
import csv
import json
import logging
import os
import random
import sys
import time
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, cast

ROOT_DIR = Path(__file__).resolve().parent


def _extend_sys_path() -> None:
    candidates = [ROOT_DIR.parent, ROOT_DIR.parent.parent, ROOT_DIR.parent.parent.parent]
    for candidate in candidates:
        package_dir = candidate / "adhash"
        if package_dir.exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break


try:  # pragma: no cover - executed only during development
    from adhash.cli.commands import CLIContext, register_subcommands
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
    from adhash.io.snapshot import (
        atomic_map_save,
        load_snapshot_any,
        save_snapshot_any,
    )
    from adhash.metrics import (  # noqa: F401
        TICK_SCHEMA,
        Metrics,
        ThresholdWatchdog,
        apply_tick_to_metrics,
        format_bucket_label,
        start_metrics_server,
        stream_metrics_file,
    )
    from adhash.workloads import analyze_workload_csv
except ModuleNotFoundError:  # pragma: no cover - fallback when running from repo root
    _extend_sys_path()
    from adhash.cli.commands import CLIContext, register_subcommands
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
    from adhash.io.snapshot import (
        atomic_map_save,
        load_snapshot_any,
        save_snapshot_any,
    )
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

    def format(self, record: logging.LogRecord) -> str:
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
    log_file: str | None = None,
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

    for handler in list(logger.handlers):
        with contextlib.suppress(Exception):
            handler.close()
        logger.removeHandler(handler)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file:
        handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
        handler.setFormatter(formatter)
        logger.addHandler(handler)


configure_logging()

APP_CONFIG: AppConfig = AppConfig()
OUTPUT_JSON: bool = False


def set_app_config(cfg: AppConfig) -> None:
    global APP_CONFIG
    APP_CONFIG = cfg


def emit_success(
    command: str, *, text: str | None = None, data: dict[str, Any] | None = None
) -> None:
    if OUTPUT_JSON:
        payload: dict[str, Any] = {"ok": True, "command": command}
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
    infile: str | None,
    outfile: str | None,
    *,
    apply_preset: str | None = None,
    save_preset_name: str | None = None,
    presets_dir: str | None = None,
    force: bool = False,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Interactive config editor that supports presets and existing files."""

    preset_dir_path: Path | None = None
    if apply_preset or save_preset_name:
        preset_dir_path = resolve_presets_dir(presets_dir)

    base_source = "defaults"
    base_cfg: AppConfig

    if apply_preset:
        if preset_dir_path is None:
            raise InvariantError("Preset directory not resolved while applying preset")
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

    target = outfile or infile or "config/config.toml"
    out_path = _write_config_file(cfg, target)
    print_fn("")
    print_fn(f"Configuration written to {out_path}")

    preset_path: Path | None = None
    if save_preset_name:
        if preset_dir_path is None:
            preset_dir_path = resolve_presets_dir(presets_dir)
        preset_path = save_preset(cfg, save_preset_name, preset_dir_path, overwrite=force)
        print_fn(f"Preset saved to {preset_path}")

    result: dict[str, Any] = {"outfile": str(out_path), "base": base_source}
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
    metrics: Metrics | None = None,
    *,
    sink: MetricsSink | None = None,
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
        chaining = TwoLevelChainingMap(
            initial_buckets=policy.initial_buckets, groups_per_bucket=policy.groups_per_bucket
        )
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
def run_op(
    m: Any, op: str, key: str | None, value: str | None, metrics: Metrics | None = None
) -> str | None:
    if op == "put":
        if key is None or value is None:
            raise ValueError("PUT operations require both key and value")
        m.put(key, value)
        if metrics:
            metrics.puts_total += 1
    elif op == "get":
        if key is None:
            raise ValueError("GET operations require a key")
        v = m.get(key)
        if metrics:
            metrics.gets_total += 1
        return "" if v is None else str(v)
    elif op == "del":
        if key is None:
            raise ValueError("DEL operations require a key")
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
    def load_ops() -> Iterator[tuple[str, str, str | None]]:
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            for i, row in enumerate(r):
                if sample_limit and i >= sample_limit:
                    break
                yield row["op"], row["key"], row.get("value") or None

    ops = list(load_ops())
    candidates: dict[str, Any] = {
        "fast-insert": build_map("fast-insert"),
        "fast-lookup": build_map("fast-lookup"),
    }
    results: dict[str, float] = {}
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
    cdf: list[float] = []
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
    return base_idx & ~mask


def generate_csv(
    out_path: str,
    ops: int,
    read_ratio: float,
    key_skew: float,
    key_space: int,
    seed: int,
    del_ratio_within_writes: float = 0.2,
    adversarial_ratio: float = 0.0,
    adversarial_lowbits: int = 6,
) -> None:
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
    rng = random.Random(seed)  # noqa: S311  # nosec B311 - deterministic workload sampler
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


def analyze_workload(path: str, top_keys: int, max_tracked_keys: int) -> Any:
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


def run_csv(
    path: str,
    mode: str,
    metrics_port: int | None = None,
    snapshot_in: str | None = None,
    snapshot_out: str | None = None,
    compress_out: bool = False,
    compact_interval: float | None = None,
    json_summary_out: str | None = None,
    latency_sample_k: int = 1000,
    latency_sample_every: int = 128,
    latency_bucket_preset: str = "default",
    metrics_out_dir: str | None = None,
    metrics_max_ticks: int | None = None,
    dry_run: bool = False,
    csv_max_rows: int = DEFAULT_CSV_MAX_ROWS,
    csv_max_bytes: int = DEFAULT_CSV_MAX_BYTES,
    metrics_host: str | None = None,
    *,
    capture_history: bool = False,
) -> dict[str, Any]:
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
                metrics_port = 0 if env_value.lower() == "auto" else _parse_port(env_value)
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
        latency_hist_preset, latency_bucket_bounds_tuple = resolve_latency_bucket_bounds(
            requested_preset
        )
    except ValueError:
        latency_hist_preset, latency_bucket_bounds_tuple = resolve_latency_bucket_bounds("default")
        logger.warning(
            "Unknown latency bucket preset '%s'; falling back to 'default'",
            requested_preset,
        )
    latency_bucket_bounds = list(latency_bucket_bounds_tuple)

    def load_ops(validate_only: bool = False) -> Iterator[tuple[str, str, str | None]]:
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
                        raise BadInputError(
                            f"Unknown op '{op_raw}' at line {line_no}", hint=csv_hint
                        )
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
        except (csv.Error, ValueError) as exc:
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

    run_result: dict[str, Any] = {
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
    history_buffer: deque[dict[str, Any]] = deque(maxlen=history_max)

    metrics = Metrics()
    metrics.history_buffer = history_buffer

    with ExitStack() as cleanup:
        server = None
        stop_server: Callable[[], None] | None = None
        bind_host = metrics_host or os.getenv("ADHASH_METRICS_HOST") or "127.0.0.1"
        if metrics_port is not None:
            try:
                server, stop_server = start_metrics_server(metrics, metrics_port, host=bind_host)
            except PermissionError:
                server = None
                stop_server = None
            if stop_server is not None:
                cleanup.callback(stop_server)
            if server is not None:
                actual_port = getattr(server, "server_port", metrics_port)
                run_result["metrics_port"] = actual_port
                run_result["metrics_host"] = bind_host

        metrics_file = None
        metrics_path: Path | None = None
        if metrics_out_dir:
            out_dir = Path(metrics_out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            file_mode = "w+" if metrics_max_ticks and metrics_max_ticks > 0 else "a"
            metrics_path = out_dir / "metrics.ndjson"
            metrics_file = cleanup.enter_context(metrics_path.open(file_mode, encoding="utf-8"))

        events: list[dict[str, Any]] = []
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
            if isinstance(snap, TwoLevelChainingMap | RobinHoodMap | HybridAdaptiveHashMap):
                m = snap
            elif isinstance(snap, dict) and "backend" in snap:
                m = HybridAdaptiveHashMap.load(snapshot_in)
            else:
                raise PolicyError("Unsupported snapshot format")
            logger.info("Loaded snapshot from %s (type=%s)", snapshot_in, type(m).__name__)
            sink.attach(m)
        else:
            m = build_map(mode, metrics=metrics, sink=sink)

        want_latency = latency_sample_k > 0 and latency_sample_every > 0
        overall_res = Reservoir(k=latency_sample_k)
        res_by_op: dict[str, Reservoir] = {
            "put": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF01),
            "get": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF02),
            "del": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF03),
        }
        overall_loop_res = Reservoir(k=latency_sample_k, seed=0xC0FF10)
        loop_res_by_op: dict[str, Reservoir] = {
            "put": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF11),
            "get": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF12),
            "del": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF13),
        }

        last_probe_hist: list[list[int]] = []
        last_key_heatmap: dict[str, Any] = {
            "rows": 0,
            "cols": 0,
            "matrix": [],
            "max": 0,
            "total": 0,
            "slot_span": 1,
            "original_slots": 0,
        }

        def percentile_packet(res: Reservoir) -> dict[str, float]:
            return res.percentiles([0.50, 0.90, 0.99])

        def reservoir_summary(res: Reservoir) -> dict[str, float] | None:
            if not res.buf:
                return None
            return {"count": float(len(res.buf)), "sum": float(sum(res.buf))}

        def reservoir_histogram(res: Reservoir) -> list[tuple[float, int]]:
            if not res.buf:
                return []
            data = sorted(res.buf)
            buckets: list[tuple[float, int]] = []
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
            reservoir_map: dict[str, Reservoir] = {"overall": overall_res}
            reservoir_map.update(res_by_op)
            latency_summary_stats: dict[str, dict[str, float]] = {}
            latency_histograms: dict[str, list[tuple[float, int]]] = {}
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
                op: [{"le": format_bucket_label(bound), "count": count} for bound, count in hist]
                for op, hist in latency_histograms.items()
            }
            loop_series_packets = {
                "overall": percentile_packet(overall_loop_res),
                "put": percentile_packet(loop_res_by_op["put"]),
                "get": percentile_packet(loop_res_by_op["get"]),
                "del": percentile_packet(loop_res_by_op["del"]),
            }
            tick["latency_loop_ms"] = loop_series_packets
            tick["latency_hist_preset"] = latency_hist_preset
            tick["events"] = list(events)
            latency_ms_dict = cast(dict[str, dict[str, float]], tick["latency_ms"])
            overall_ms = latency_ms_dict.get("overall", {})
            latency_ns = {q: int(max(value, 0.0) * 1_000_000) for q, value in overall_ms.items()}
            tick["latency_ns"] = latency_ns
            elapsed = tick["t"]
            implied_latency_ms: float | None = None
            if isinstance(elapsed, int | float) and elapsed > 0.0 and metrics.ops_total > 0:
                throughput_avg = metrics.ops_total / elapsed
                if throughput_avg > 0.0:
                    implied_latency_ms = 1000.0 / throughput_avg
            tick["implied_latency_ms"] = implied_latency_ms
            loop_packet = loop_series_packets.get("overall")
            loop_median: float | None = None
            if isinstance(loop_packet, Mapping):
                raw_median = loop_packet.get("p50")
                if isinstance(raw_median, int | float):
                    loop_median = float(raw_median)
            tick["loop_latency_median_ms"] = loop_median

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
                if (
                    history_buffer
                    and len(history_buffer)
                    and history_buffer[-1].get("state") == "idle"
                ):
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

        for op_idx, (op, k, v) in enumerate(load_ops(), 1):
            sample_iteration = want_latency and (op_idx % latency_sample_every == 0)
            loop_start = time.perf_counter() if sample_iteration else None

            if sample_iteration:
                run_op(m, op, k, v, metrics=metrics)
                backend_elapsed_ms = (time.perf_counter() - cast(float, loop_start)) * 1000.0
                overall_res.offer(backend_elapsed_ms)
                if op in res_by_op:
                    res_by_op[op].offer(backend_elapsed_ms)
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
                        if m.trigger_compaction():
                            logger.info(
                                "Proactive compaction tick (interval=%.2fs)", compact_interval
                            )
                            sink.inc_compactions()
                            sink.record_event(
                                "compaction", {"backend": backend_name, "source": "proactive"}
                            )
                    elif isinstance(m, RobinHoodMap):
                        logger.info("Proactive compaction tick (interval=%.2fs)", compact_interval)
                        m.compact()
                        sink.inc_compactions()
                        sink.record_event(
                            "compaction", {"backend": backend_name, "source": "proactive"}
                        )
            if sample_iteration and loop_start is not None:
                loop_elapsed_ms = (time.perf_counter() - loop_start) * 1000.0
                overall_loop_res.offer(loop_elapsed_ms)
                if op in loop_res_by_op:
                    loop_res_by_op[op].offer(loop_elapsed_ms)

        sink.record_event(
            "complete",
            {"backend": metrics.backend_name, "message": "workload completed"},
        )
        emit_tick(force_sample=True)
        elapsed = time.perf_counter() - start
        logger.info("run-csv finished in %.6f s, backend=%s", elapsed, metrics.backend_name)

        summary: dict[str, Any] = {
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
            "latency_loop_ms": {
                "overall": percentile_packet(overall_loop_res),
                "put": percentile_packet(loop_res_by_op["put"]),
                "get": percentile_packet(loop_res_by_op["get"]),
                "del": percentile_packet(loop_res_by_op["del"]),
            },
            "latency_sample": {
                "reservoir_k_overall": overall_res.k,
                "reservoir_k_each": res_by_op["put"].k,
                "seen_overall": overall_res.n,
                "every_n_ops": latency_sample_every,
            },
            "latency_histogram_preset": latency_hist_preset,
        }
        ops_per_second = summary.get("ops_per_second")
        ops_per_second_value = (
            float(ops_per_second) if isinstance(ops_per_second, int | float) else None
        )
        implied_latency_ms = (
            (1000.0 / ops_per_second_value)
            if ops_per_second_value and ops_per_second_value > 0
            else None
        )
        summary["implied_latency_ms"] = implied_latency_ms
        latency_loop_any = summary.get("latency_loop_ms")
        loop_packet = (
            latency_loop_any.get("overall") if isinstance(latency_loop_any, dict) else None
        )
        raw_loop_median = loop_packet.get("p50") if isinstance(loop_packet, dict) else None
        loop_median_ms = (
            float(raw_loop_median) if isinstance(raw_loop_median, int | float) else None
        )
        summary["loop_latency_median_ms"] = loop_median_ms

        run_result.update({
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
            "latency_loop_ms": summary["latency_loop_ms"],
            "implied_latency_ms": implied_latency_ms,
            "loop_latency_median_ms": loop_median_ms,
            "summary": summary,
        })

        if metrics_path is not None:
            run_result["metrics_file"] = str(metrics_path)

        if capture_history:
            run_result["history"] = [dict(item) for item in history_buffer]

        if json_summary_out:
            with open(json_summary_out, "w") as jf:
                json.dump(summary, jf, indent=2)
            logger.info("Wrote JSON summary: %s", json_summary_out)

        if snapshot_out:
            if isinstance(m, TwoLevelChainingMap | RobinHoodMap | HybridAdaptiveHashMap):
                atomic_map_save(m, Path(snapshot_out), compress=compress_out)
            else:
                save_snapshot_any(m, snapshot_out, compress_out)  # type: ignore[unreachable]
            logger.info("Wrote snapshot to %s (compress=%s)", snapshot_out, compress_out)
            run_result["snapshot_written"] = snapshot_out

        return run_result


def _safe_number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _delta_packet(baseline: float | None, candidate: float | None) -> dict[str, float | None]:
    delta: float | None = None
    percent: float | None = None
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


def _latency_deltas(
    baseline_summary: dict[str, Any], candidate_summary: dict[str, Any]
) -> dict[str, dict[str, dict[str, float | None]]]:
    output: dict[str, dict[str, dict[str, float | None]]] = {}
    baseline_packet = (
        baseline_summary.get("latency_ms", {}) if isinstance(baseline_summary, dict) else {}
    )
    candidate_packet = (
        candidate_summary.get("latency_ms", {}) if isinstance(candidate_summary, dict) else {}
    )
    for operation in sorted(set(baseline_packet.keys()) | set(candidate_packet.keys())):
        base_series = (
            baseline_packet.get(operation, {})
            if isinstance(baseline_packet.get(operation), dict)
            else {}
        )
        cand_series = (
            candidate_packet.get(operation, {})
            if isinstance(candidate_packet.get(operation), dict)
            else {}
        )
        output[operation] = {}
        for quantile in sorted(
            set(base_series.keys()) | set(cand_series.keys()) | {"p50", "p90", "p99"}
        ):
            output[operation][quantile] = _delta_packet(
                _safe_number(base_series.get(quantile)),
                _safe_number(cand_series.get(quantile)),
            )
    return output


def _build_timeline(
    baseline_history: list[dict[str, Any]],
    candidate_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    length = min(len(baseline_history), len(candidate_history))
    timeline: list[dict[str, Any]] = []
    for index in range(length):
        base_tick = baseline_history[index]
        cand_tick = candidate_history[index]
        base_ops = _safe_number(base_tick.get("ops_per_second_ema")) or _safe_number(
            base_tick.get("ops_per_second_instant")
        )
        cand_ops = _safe_number(cand_tick.get("ops_per_second_ema")) or _safe_number(
            cand_tick.get("ops_per_second_instant")
        )
        base_load = _safe_number(base_tick.get("load_factor"))
        cand_load = _safe_number(cand_tick.get("load_factor"))
        base_probe = _safe_number(base_tick.get("avg_probe_estimate"))
        cand_probe = _safe_number(cand_tick.get("avg_probe_estimate"))
        entry: dict[str, Any] = {
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
    baseline_config: str | None = None,
    candidate_config: str | None = None,
    latency_sample_k: int = 1000,
    latency_sample_every: int = 128,
    metrics_max_ticks: int | None = None,
    metrics_dir: str | None = None,
    json_out: str | None = None,
    markdown_out: str | None = None,
) -> dict[str, Any]:
    """Run two ``run-csv`` replays and compute throughput / latency deltas."""

    artifact_dir = Path(metrics_dir).expanduser().resolve() if metrics_dir else None
    if artifact_dir:
        artifact_dir.mkdir(parents=True, exist_ok=True)

    original_cfg = clone_config(APP_CONFIG)

    def _prepare_config(path: str | None) -> AppConfig:
        if path:
            return clone_config(load_app_config(path))
        return clone_config(original_cfg)

    baseline_cfg = _prepare_config(baseline_config)
    candidate_cfg = _prepare_config(candidate_config)

    def _run(tag: str, label: str, mode: str, cfg: AppConfig) -> dict[str, Any]:
        set_app_config(cfg)
        json_summary_path: Path | None = None
        metrics_out: str | None = None
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
        return {
            "label": label,
            "mode": mode,
            "config_path": config_resolved,
            "summary": result.get("summary", {}),
            "events": result.get("events", []),
            "metrics_file": result.get("metrics_file"),
            "history": history,
        }

    baseline_payload = _run("baseline", baseline_label, baseline_mode, baseline_cfg)
    candidate_payload = _run("candidate", candidate_label, candidate_mode, candidate_cfg)

    set_app_config(original_cfg)

    baseline_summary = baseline_payload["summary"]
    candidate_summary = candidate_payload["summary"]

    ops_delta = _delta_packet(
        _safe_number(baseline_summary.get("ops_per_second")),
        _safe_number(candidate_summary.get("ops_per_second")),
    )
    elapsed_delta = _delta_packet(
        _safe_number(baseline_summary.get("elapsed_seconds")),
        _safe_number(candidate_summary.get("elapsed_seconds")),
    )
    migrations_delta = _delta_packet(
        _safe_number(baseline_summary.get("migrations_triggered")),
        _safe_number(candidate_summary.get("migrations_triggered")),
    )
    compactions_delta = _delta_packet(
        _safe_number(baseline_summary.get("compactions_triggered")),
        _safe_number(candidate_summary.get("compactions_triggered")),
    )

    latency_delta = _latency_deltas(baseline_summary, candidate_summary)
    timeline = _build_timeline(baseline_payload["history"], candidate_payload["history"])

    baseline_payload.pop("history", None)
    candidate_payload.pop("history", None)

    comparison: dict[str, Any] = {
        "schema": "adhash.compare.v1",
        "metadata": {
            "csv": Path(csv).resolve().as_posix(),
            "generated_at": (
                datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            ),
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

        def format_delta_row(label: str, packet: dict[str, Any], fmt: str) -> str:
            baseline_val = packet.get("baseline") or 0
            candidate_val = packet.get("candidate") or 0
            delta_val = packet.get("delta") or 0
            percent_val = packet.get("percent") or 0
            return (
                f"| {label} | {baseline_val:{fmt}} | {candidate_val:{fmt}} | "
                f"{delta_val:{fmt}} | {percent_val:.2f}% |"
            )

        lines = [
            f"# A/B Comparison — {baseline_label} vs {candidate_label}",
            "",
            f"* CSV: `{Path(csv).resolve().as_posix()}`",
            f"* Generated: {comparison['metadata']['generated_at']}",
            "",
            "| Metric | Baseline | Candidate | Δ | % |",
            "|---|---:|---:|---:|---:|",
            format_delta_row("Ops/s", ops_delta, ".2f"),
            format_delta_row("Runtime (s)", elapsed_delta, ".2f"),
            format_delta_row("Migrations", migrations_delta, ".0f"),
            format_delta_row("Compactions", compactions_delta, ".0f"),
            "",
            "## Latency (overall)",
            "",
            "| Percentile | Baseline (ms) | Candidate (ms) | Δ (ms) | % |",
            "|---|---:|---:|---:|---:|",
        ]
        overall_latency = latency_delta.get("overall", {})
        for quantile in ("p50", "p90", "p99"):
            packet = overall_latency.get(quantile, {})
            baseline_ms = packet.get("baseline") or 0
            candidate_ms = packet.get("candidate") or 0
            delta_ms = packet.get("delta") or 0
            percent_ms = packet.get("percent") or 0
            lines.append(
                f"| {quantile} | {baseline_ms:.3f} | {candidate_ms:.3f} | "
                f"{delta_ms:.3f} | {percent_ms:.2f}% |"
            )
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        comparison["metadata"]["comparison_markdown"] = md_path.as_posix()

    if artifact_dir:
        comparison["metadata"]["artifact_dir"] = artifact_dir.as_posix()

    return comparison


# --------------------------------------------------------------------
# Verification (with optional repair)
# --------------------------------------------------------------------
def _verify_chaining(m: TwoLevelChainingMap, verbose: bool) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    total = 0
    for groups in m._buckets:
        for grp in groups:
            total += len(grp)
    ok = total == m._size
    if not ok:
        msgs.append(f"Size mismatch: size={m._size}, summed={total}")
    if verbose:
        msgs.append(
            f"Buckets={m.M}, Groups/Bucket={m.G}, Size={m._size}, MaxGroupLen={m.max_group_len()}"
        )
    return ok, msgs


def _verify_robinhood(m: RobinHoodMap, verbose: bool) -> tuple[bool, list[str]]:
    msgs: list[str] = []
    bound_ok = (m._size + m._tombstones) <= m._cap
    if not bound_ok:
        msgs.append(f"Bound violated: size+tombstones={m._size + m._tombstones} > cap={m._cap}")
    count = sum(1 for _ in m.items())
    size_ok = count == m._size
    if not size_ok:
        msgs.append(f"Item iteration count={count} != size={m._size}")
    if verbose:
        msgs.append(
            f"Cap={m._cap}, Size={m._size}, Tombstones={m._tombstones}, "
            f"LF={m.load_factor():.3f}, TZ={m.tombstone_ratio():.3f}"
        )
    return (bound_ok and size_ok), msgs


def _verify_hybrid(m: HybridAdaptiveHashMap, verbose: bool) -> tuple[bool, list[str]]:
    msgs: list[str] = []
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


def verify_snapshot(
    path: str, verbose: bool = False, repair: bool = False, repair_out: str | None = None
) -> int:
    """
    Verify invariants of a snapshot. If --repair is passed and the map is a RobinHoodMap
    (or Hybrid with RH active), compacts to purge tombstones / fix counters and writes
    to --out if provided (else in-place rewrite).
    """
    try:
        snap = load_snapshot_any(path)
    except (ValueError, OSError, RuntimeError) as e:
        print(f"ERROR: failed to load snapshot: {e}")
        return 1

    def write_snapshot(obj: Any, out_path: str) -> None:
        save_snapshot_any(obj, out_path, compress=out_path.endswith(".gz"))

    ok = False
    messages: list[str] = []

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
        except (ValueError, OSError, RuntimeError) as e:
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
            if isinstance(snap, TwoLevelChainingMap | RobinHoodMap):
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
        except (ValueError, OSError, RuntimeError) as e:
            print(f"ERROR: repair failed: {e}")
            return 1
    elif repair and target_for_repair is None:
        print(
            "NOTICE: --repair requested but snapshot/backend is not a RobinHoodMap; "
            "no safe repair applicable."
        )

    return 0 if ok else 1


# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------
def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(
        description=(
            "HashMap CLI with multi-backend, adaptive mode, generator, profiler, "
            "metrics, snapshots, verification (with repair), and CI summaries."
        )
    )
    p.add_argument(
        "--mode",
        default="adaptive",
        choices=["fast-insert", "fast-lookup", "memory-tight", "adaptive"],
        help="Select backend when not loading a snapshot.",
    )
    p.add_argument("--log-json", action="store_true", help="Emit logs in JSON format")
    p.add_argument(
        "--log-file",
        default=None,
        help="Optional log file path (rotates at 5MB, keeps 5 backups by default)",
    )
    p.add_argument(
        "--log-max-bytes",
        type=int,
        default=DEFAULT_LOG_MAX_BYTES,
        help="Max bytes per log file before rotation (default: %(default)s)",
    )
    p.add_argument(
        "--log-backup-count",
        type=int,
        default=DEFAULT_LOG_BACKUP_COUNT,
        help="Number of rotated log files to keep (default: %(default)s)",
    )
    p.add_argument(
        "--json", action="store_true", help="Emit machine-readable success output to stdout"
    )
    p.add_argument(
        "--config",
        default=None,
        help="Path to TOML config file (overrides defaults and env overrides)",
    )
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
    except Exception as e:  # noqa: BLE001
        logger.exception("Fatal error: %s", e)
        raise SystemExit(2) from e


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # noqa: BLE001
        logger.exception("Fatal error: %s", e)
        sys.exit(2)
