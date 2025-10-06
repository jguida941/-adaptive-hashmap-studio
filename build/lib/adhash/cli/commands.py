
"""CLI command registration and handlers for Adaptive Hash Map."""

from __future__ import annotations

import argparse
import ast
import io
import json
import logging
import threading
import time
from collections import deque
from contextlib import redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple, Type

from adhash.contracts.error import Exit, IOErrorEnvelope, InvariantError
from adhash.config_toolkit import list_presets, resolve_presets_dir
from adhash.io.snapshot import atomic_map_save, load_snapshot_any
from adhash.io.snapshot_header import describe_snapshot
from adhash.metrics import Metrics, apply_tick_to_metrics, start_metrics_server, stream_metrics_file
from adhash.workloads import WorkloadDNAResult, format_workload_dna


@dataclass(frozen=True)
class CLIContext:
    """Runtime hooks supplied by the top-level CLI entrypoint."""

    emit_success: Callable[..., None]
    build_map: Callable[[str], Any]
    run_op: Callable[..., Optional[str]]
    profile_csv: Callable[[str], str]
    run_csv: Callable[..., Dict[str, Any]]
    generate_csv: Callable[..., None]
    run_config_wizard: Callable[[str], Path]
    run_config_editor: Callable[..., Dict[str, Any]]
    run_ab_compare: Callable[..., Dict[str, Any]]
    verify_snapshot: Callable[..., int]
    analyze_workload: Callable[[str, int, int], WorkloadDNAResult]
    invoke_main: Callable[[List[str]], int]
    logger: logging.Logger
    json_enabled: Callable[[], bool]
    robinhood_cls: Type[Any]
    guard: Callable[[Callable[[argparse.Namespace], int]], Callable[[argparse.Namespace], int]]
    latency_bucket_choices: List[str]


def register_subcommands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    ctx: CLIContext,
) -> Dict[str, Callable[[argparse.Namespace], int]]:
    """Define CLI subcommands and return their handlers."""

    handlers: Dict[str, Callable[[argparse.Namespace], int]] = {}

    def _register(name: str, help_text: Optional[str], configure: Callable[[argparse.ArgumentParser], Callable[[argparse.Namespace], int]]) -> None:
        parser = subparsers.add_parser(name, help=help_text)
        handler = configure(parser)
        handlers[name] = ctx.guard(handler)

    _register("put", None, lambda parser: _configure_put(parser, ctx))
    _register("get", None, lambda parser: _configure_get(parser, ctx))
    _register("del", None, lambda parser: _configure_del(parser, ctx))
    _register("items", None, lambda parser: _configure_items(parser, ctx))
    _register("profile", "Profile a CSV workload and print recommended backend.", lambda parser: _configure_profile(parser, ctx))
    _register("generate-csv", "Generate a synthetic workload CSV.", lambda parser: _configure_generate(parser, ctx))
    _register("run-csv", "Replay a CSV workload (metrics, snapshots, compaction, JSON summary).", lambda parser: _configure_run_csv(parser, ctx))
    _register(
        "workload-dna",
        "Analyze a CSV workload for ratios, skew, and collision risk.",
        lambda parser: _configure_workload_dna(parser, ctx),
    )
    _register(
        "inspect-snapshot",
        "Inspect snapshot metadata and optionally search for keys.",
        lambda parser: _configure_inspect_snapshot(parser, ctx),
    )
    _register("config-wizard", "Interactively generate a TOML config file.", lambda parser: _configure_config_wizard(parser, ctx))
    _register(
        "config-edit",
        "Edit a config file with preset support using the wizard schema.",
        lambda parser: _configure_config_edit(parser, ctx),
    )
    _register(
        "ab-compare",
        "Run paired run-csv jobs and compute throughput/latency deltas.",
        lambda parser: _configure_ab_compare(parser, ctx),
    )
    _register("mission-control", "Launch the Mission Control desktop UI (PyQt6).", lambda parser: _configure_mission_control(parser, ctx))
    _register("serve", "Serve the dashboard/metrics API without running a workload.", lambda parser: _configure_serve(parser, ctx))
    _register("compact-snapshot", "Compact a RobinHoodMap snapshot offline.", lambda parser: _configure_compact_snapshot(parser, ctx))
    _register("verify-snapshot", "Verify invariants of a snapshot; optional safe repair (RobinHoodMap).", lambda parser: _configure_verify_snapshot(parser, ctx))

    return handlers


def _configure_put(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("key")
    parser.add_argument("value")

    def handler(args: argparse.Namespace) -> int:
        m = ctx.build_map(args.mode)
        out = ctx.run_op(m, "put", args.key, args.value)
        data = {"mode": args.mode, "key": args.key, "value": args.value}
        if out is not None:
            data["result"] = out
        ctx.emit_success("put", text=out, data=data)
        return int(Exit.OK)

    return handler


def _configure_get(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("key")

    def handler(args: argparse.Namespace) -> int:
        m = ctx.build_map(args.mode)
        out = ctx.run_op(m, "get", args.key, None)
        value = out if out not in {None, ""} else None
        data = {
            "mode": args.mode,
            "key": args.key,
            "found": bool(value),
            "value": value,
        }
        ctx.emit_success("get", text=out, data=data)
        return int(Exit.OK)

    return handler


def _configure_del(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("key")

    def handler(args: argparse.Namespace) -> int:
        m = ctx.build_map(args.mode)
        out = ctx.run_op(m, "del", args.key, None)
        deleted = out == "1"
        data = {"mode": args.mode, "key": args.key, "deleted": deleted}
        ctx.emit_success("del", text=out, data=data)
        return int(Exit.OK)

    return handler


def _configure_items(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:

    def handler(args: argparse.Namespace) -> int:
        m = ctx.build_map(args.mode)
        out = ctx.run_op(m, "items", None, None)
        items = _parse_items_output(out)
        data = {"mode": args.mode, "count": len(items), "items": items}
        ctx.emit_success("items", text=out, data=data)
        return int(Exit.OK)

    return handler


def _configure_profile(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--csv", required=True)
    parser.add_argument("--then", nargs=argparse.REMAINDER, help="After profiling, run one command with the picked mode.")

    def handler(args: argparse.Namespace) -> int:
        pick = ctx.profile_csv(args.csv)
        ctx.emit_success("profile", text=pick, data={"csv": args.csv, "recommended_mode": pick})
        if args.then:
            return ctx.invoke_main(["--mode", pick] + args.then)
        return int(Exit.OK)

    return handler


def _configure_generate(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--outfile", required=True)
    parser.add_argument("--ops", type=int, default=100000)
    parser.add_argument("--read-ratio", type=float, default=0.8)
    parser.add_argument("--key-skew", type=float, default=0.0)
    parser.add_argument("--key-space", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--del-ratio", type=float, default=0.2)
    parser.add_argument("--adversarial-ratio", type=float, default=0.0)
    parser.add_argument("--adversarial-lowbits", type=int, default=6)

    def handler(args: argparse.Namespace) -> int:
        try:
            ctx.generate_csv(
                args.outfile,
                args.ops,
                args.read_ratio,
                args.key_skew,
                args.key_space,
                args.seed,
                del_ratio_within_writes=args.del_ratio,
                adversarial_ratio=args.adversarial_ratio,
                adversarial_lowbits=args.adversarial_lowbits,
            )
        except OSError as exc:
            raise IOErrorEnvelope(str(exc)) from exc
        ctx.logger.info("Wrote workload CSV: %s", args.outfile)
        ctx.emit_success(
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

    return handler


def _configure_run_csv(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--csv", required=True)
    parser.add_argument("--metrics-port", type=int, default=None)
    parser.add_argument(
        "--metrics-out-dir",
        type=str,
        default=None,
        help="Directory for metrics.ndjson (schema exported by metrics module)",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate the CSV workload and exit without executing it")
    parser.add_argument("--csv-max-rows", type=int, default=5_000_000,
                        help="Abort if CSV rows exceed this count (0 disables check)")
    parser.add_argument("--csv-max-bytes", type=int, default=500 * 1024 * 1024,
                        help="Abort if CSV file size exceeds this many bytes (0 disables check)")
    parser.add_argument("--metrics-max-ticks", type=int, default=None,
                        help="Optional retention limit for metrics.ndjson (keep last N ticks)")
    parser.add_argument("--snapshot-in", type=str, default=None, help="Load initial snapshot (.gz auto-detected)")
    parser.add_argument("--snapshot-out", type=str, default=None, help="Write snapshot after run")
    parser.add_argument("--compress", action="store_true", help="Gzip-compress snapshot writes or use .gz suffix")
    parser.add_argument("--compact-interval", type=float, default=None, help="Seconds between proactive compactions")
    parser.add_argument("--json-summary-out", type=str, default=None, help="Write final run stats to JSON for CI")
    parser.add_argument("--latency-sample-k", type=int, default=1000, help="Reservoir size for latency sampling")
    parser.add_argument("--latency-sample-every", type=int, default=128, help="Sample every Nth operation")
    parser.add_argument(
        "--latency-buckets",
        choices=ctx.latency_bucket_choices,
        default="default",
        help="Latency histogram bucket preset (default: %(default)s)",
    )

    def handler(args: argparse.Namespace) -> int:
        result = ctx.run_csv(
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
        ctx.emit_success("run-csv", data=result)
        return int(Exit.OK)

    return handler


def _configure_workload_dna(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--csv", required=True, help="CSV workload to inspect")
    parser.add_argument(
        "--top-keys", type=int, default=10, help="Number of hot keys to report (default: %(default)s)"
    )
    parser.add_argument(
        "--max-tracked-keys",
        type=int,
        default=200_000,
        help="Upper bound on keys tracked for heavy-hitter detection (default: %(default)s)",
    )
    parser.add_argument(
        "--json-out",
        help="Optional file to write the DNA summary as JSON (indentation matches --pretty)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output (stdout when --json and --json-out are absent)",
    )

    def handler(args: argparse.Namespace) -> int:
        result = ctx.analyze_workload(args.csv, args.top_keys, args.max_tracked_keys)
        payload = result.to_dict()

        if args.json_out:
            Path(args.json_out).expanduser().write_text(
                json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
                + "\n",
                encoding="utf-8",
            )

        summary_text = format_workload_dna(result)

        if ctx.json_enabled():
            ctx.emit_success("workload-dna", data={"dna": payload})
        else:
            ctx.emit_success("workload-dna", text=summary_text, data={"dna": payload})

        return int(Exit.OK)

    return handler


def _configure_inspect_snapshot(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--in", dest="path", required=True, help="Snapshot file (.pkl or .pkl.gz)")
    parser.add_argument("--key", help="Exact key to search (literal evaluated if possible)")
    parser.add_argument("--contains", default=None, help="Filter preview keys containing this substring")
    parser.add_argument("--limit", type=int, default=20, help="Preview entry limit (default: %(default)s)")

    def handler(args: argparse.Namespace) -> int:
        path = Path(args.path).expanduser().resolve()
        if not path.exists():
            raise IOErrorEnvelope(f"Snapshot not found: {path}")

        try:
            descriptor = describe_snapshot(path)
        except Exception as exc:  # pragma: no cover - defensive
            raise IOErrorEnvelope(f"Failed to parse snapshot header: {exc}") from exc

        try:
            payload = load_snapshot_any(str(path))
        except Exception as exc:  # pragma: no cover - defensive
            raise IOErrorEnvelope(f"Failed to load snapshot payload: {exc}") from exc

        header = descriptor.header
        header_data: Dict[str, Any] = {
            "version": header.version,
            "compressed": descriptor.compressed,
            "checksum_hex": descriptor.checksum_hex,
            "payload_bytes": header.payload_len,
            "checksum_bytes": header.checksum_len,
            "file_bytes": path.stat().st_size,
        }

        object_data: Dict[str, Any] = {"type": type(payload).__name__}
        try:
            object_data["size"] = len(payload)  # type: ignore[arg-type]
        except Exception:
            pass
        if hasattr(payload, "backend_name"):
            try:
                object_data["backend"] = payload.backend_name()
            except Exception:
                pass
        for attr, label in (
            ("load_factor", "load_factor"),
            ("tombstone_ratio", "tombstone_ratio"),
            ("max_group_len", "max_group_len"),
        ):
            fn = getattr(payload, attr, None)
            if callable(fn):
                try:
                    value = fn()
                except Exception:
                    continue
                if isinstance(value, (int, float)):
                    object_data[label] = float(value)

        limit = max(args.limit, 1)
        filter_text = (args.contains or "").strip().lower() or None
        preview: List[Dict[str, Any]] = []
        try:
            for key, value in _iter_snapshot_items(payload):
                key_text = str(key)
                if filter_text and filter_text not in key_text.lower():
                    continue
                preview.append({"key": key_text, "value": _repr_trim(value)})
                if len(preview) >= limit:
                    break
        except Exception as exc:  # pragma: no cover - defensive
            preview = [{"error": f"Failed to iterate snapshot entries: {exc}"}]

        key_result: Optional[Dict[str, Any]] = None
        if args.key:
            parsed = _parse_literal(args.key)
            value, found = _lookup_snapshot_value(payload, parsed)
            key_result = {
                "input": args.key,
                "parsed": parsed,
                "found": found,
                "value": _repr_trim(value) if found else None,
            }

        data: Dict[str, Any] = {
            "path": str(path),
            "header": header_data,
            "object": object_data,
            "preview": preview,
        }
        if key_result is not None:
            data["key"] = key_result

        text_lines = [
            f"Snapshot: {path}",
            f"Version {header.version} | compressed: {'yes' if descriptor.compressed else 'no'}",
            f"Payload bytes: {header.payload_len:,} (checksum bytes: {header.checksum_len})",
            f"Checksum: {descriptor.checksum_hex}",
            f"Object type: {object_data.get('type')}",
        ]
        if "size" in object_data:
            text_lines.append(f"Items: {object_data['size']:,}")
        if "backend" in object_data:
            text_lines.append(f"Backend: {object_data['backend']}")
        for field in ("load_factor", "tombstone_ratio", "max_group_len"):
            if field in object_data:
                text_lines.append(f"{field.replace('_', ' ').title()}: {object_data[field]}")
        if preview:
            if "error" in preview[0]:
                text_lines.append(preview[0]["error"])
            else:
                text_lines.append("Preview:")
                for entry in preview[:5]:
                    text_lines.append(f"  {entry['key']} -> {entry['value']}")
        if key_result is not None:
            if key_result["found"]:
                text_lines.append(f"Key {key_result['parsed']!r} => {key_result['value']}")
            else:
                text_lines.append(f"Key {key_result['parsed']!r} not found")

        ctx.emit_success("inspect-snapshot", text="\n".join(text_lines), data=data)
        return int(Exit.OK)

    return handler


def _iter_snapshot_items(payload: Any) -> Iterable[Tuple[Any, Any]]:
    items = getattr(payload, "items", None)
    if callable(items):
        try:
            it = items()
            if isinstance(it, Iterable):
                return it
        except Exception:
            pass
    if isinstance(payload, dict):
        return payload.items()
    return []


def _lookup_snapshot_value(payload: Any, key: Any) -> Tuple[Any, bool]:
    getter = getattr(payload, "get", None)
    if callable(getter):
        try:
            value = getter(key)
            if value is not None:
                return value, True
        except Exception:
            pass
    for candidate, value in _iter_snapshot_items(payload):
        if candidate == key:
            return value, True
    return None, False


def _repr_trim(value: Any, limit: int = 160) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_literal(text: str) -> Any:
    try:
        return ast.literal_eval(text)
    except Exception:
        return text


def _configure_config_wizard(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument(
        "--outfile",
        default="config.generated.toml",
        help="Where to write the generated config (default: %(default)s)",
    )

    def handler(args: argparse.Namespace) -> int:
        out_path = ctx.run_config_wizard(args.outfile)
        ctx.emit_success(
            "config-wizard",
            text=f"Configuration written to {out_path}",
            data={"outfile": str(out_path)},
        )
        return int(Exit.OK)

    return handler


def _configure_config_edit(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument(
        "--infile",
        default="config.toml",
        help="Existing config file to load (default: %(default)s)",
    )
    parser.add_argument(
        "--outfile",
        default=None,
        help="Where to write the updated config (default: overwrite --infile or config.toml)",
    )
    parser.add_argument("--apply-preset", default=None, help="Optional preset name/path to use as the starting point")
    parser.add_argument("--save-preset", default=None, help="Optional preset name to save after editing")
    parser.add_argument("--presets-dir", default=None, help="Directory for presets (default: ~/.adhash/presets or ADHASH_PRESETS_DIR)")
    parser.add_argument("--force", action="store_true", help="Overwrite preset when --save-preset already exists")
    parser.add_argument("--list-presets", action="store_true", help="List presets and exit")

    def handler(args: argparse.Namespace) -> int:
        if args.list_presets:
            dir_path = resolve_presets_dir(args.presets_dir)
            presets = list_presets(dir_path)
            if not ctx.json_enabled():
                if presets:
                    print(f"Presets in {dir_path}:")
                    for name in presets:
                        print(f"  - {name}")
                else:
                    print(f"No presets found in {dir_path}")
            ctx.emit_success(
                "config-edit",
                data={
                    "action": "list-presets",
                    "presets_dir": str(dir_path),
                    "presets": presets,
                },
            )
            return int(Exit.OK)

        result = ctx.run_config_editor(
            args.infile,
            args.outfile,
            apply_preset=args.apply_preset,
            save_preset_name=args.save_preset,
            presets_dir=args.presets_dir,
            force=args.force,
        )
        ctx.emit_success("config-edit", data=result)
        return int(Exit.OK)

    return handler


def _configure_ab_compare(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--csv", required=True, help="CSV workload to replay for both runs")
    parser.add_argument("--baseline-label", default="baseline", help="Friendly label for the baseline run")
    parser.add_argument("--candidate-label", default="candidate", help="Friendly label for the candidate run")
    parser.add_argument(
        "--baseline-mode",
        default="adaptive",
        choices=["adaptive", "fast-insert", "fast-lookup", "memory-tight"],
        help="Backend mode for the baseline run",
    )
    parser.add_argument(
        "--candidate-mode",
        default="adaptive",
        choices=["adaptive", "fast-insert", "fast-lookup", "memory-tight"],
        help="Backend mode for the candidate run",
    )
    parser.add_argument("--baseline-config", help="Config TOML applied to the baseline run")
    parser.add_argument("--candidate-config", help="Config TOML applied to the candidate run")
    parser.add_argument("--latency-sample-k", type=int, default=1000, help="Reservoir size for latency sampling")
    parser.add_argument("--latency-sample-every", type=int, default=128, help="Sample every Nth operation")
    parser.add_argument("--metrics-max-ticks", type=int, default=None, help="Limit history buffer for metrics output")
    parser.add_argument("--out-dir", default="results/ab", help="Directory for comparison artifacts")
    parser.add_argument("--json-out", help="Override path for the comparison JSON artifact")
    parser.add_argument("--markdown-out", help="Optional Markdown summary path")
    parser.add_argument("--metrics-dir", help="Directory for per-run metrics artifacts (defaults under --out-dir)")
    parser.add_argument("--no-artifacts", action="store_true", help="Skip writing metrics summaries / presets")

    def handler(args: argparse.Namespace) -> int:
        out_dir = Path(args.out_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(args.csv).stem or "workload"
        base_slug = args.baseline_label.replace(" ", "_")
        cand_slug = args.candidate_label.replace(" ", "_")
        comparison_slug = f"{stem}_{base_slug}_vs_{cand_slug}".strip("_") or "comparison"

        if args.json_out:
            json_out = Path(args.json_out).expanduser().resolve()
        else:
            json_out = out_dir / f"{comparison_slug}.json"

        if args.markdown_out:
            markdown_out = Path(args.markdown_out).expanduser().resolve()
        else:
            markdown_out = out_dir / f"{comparison_slug}.md"

        if args.no_artifacts:
            metrics_dir: Optional[Path] = None
            markdown_path: Optional[str] = None if args.markdown_out is None else markdown_out.as_posix()
        else:
            metrics_dir = Path(args.metrics_dir).expanduser().resolve() if args.metrics_dir else out_dir / "artifacts"
            metrics_dir.mkdir(parents=True, exist_ok=True)
            markdown_path = markdown_out.as_posix()

        result = ctx.run_ab_compare(
            args.csv,
            baseline_label=args.baseline_label,
            candidate_label=args.candidate_label,
            baseline_mode=args.baseline_mode,
            candidate_mode=args.candidate_mode,
            baseline_config=args.baseline_config,
            candidate_config=args.candidate_config,
            latency_sample_k=args.latency_sample_k,
            latency_sample_every=args.latency_sample_every,
            metrics_max_ticks=args.metrics_max_ticks,
            metrics_dir=metrics_dir.as_posix() if metrics_dir is not None else None,
            json_out=json_out.as_posix() if json_out else None,
            markdown_out=markdown_path,
        )

        ctx.emit_success("ab-compare", data=result)
        return int(Exit.OK)

    return handler


def _configure_mission_control(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:

    def handler(args: argparse.Namespace) -> int:
        from adhash.mission_control.app import run_mission_control

        return int(run_mission_control([]))

    return handler


def _configure_serve(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--port", type=int, default=9090, help="Port for the metrics server (default: %(default)s)")
    parser.add_argument("--host", default="127.0.0.1", help="Host/interface to bind (default: %(default)s)")
    parser.add_argument("--source", default=None, help="Optional metrics NDJSON file to load")
    parser.add_argument("--follow", action="store_true", help="Tail the metrics source for new ticks")
    parser.add_argument("--history-limit", type=int, default=360, help="History buffer length for dashboard plots")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between tail polls when following")
    parser.add_argument("--compare", default=None, help="Optional comparison JSON produced by ab-compare")

    def handler(args: argparse.Namespace) -> int:
        history_limit = args.history_limit if args.history_limit and args.history_limit > 0 else 360
        history: Deque[Dict[str, Any]] = deque(maxlen=history_limit)

        metrics = Metrics()
        metrics.history_buffer = history
        comparison_payload = None
        if args.compare:
            compare_path = Path(args.compare).expanduser().resolve()
            if not compare_path.exists():
                raise IOErrorEnvelope(f"Comparison file not found: {compare_path}")
            try:
                comparison_payload = json.loads(compare_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise IOErrorEnvelope(f"Failed to parse comparison JSON: {exc}") from exc
            ctx.logger.info("Loaded comparison summary from %s", compare_path)

        server, stop_server = start_metrics_server(metrics, args.port, host=args.host, comparison=comparison_payload)
        ctx.logger.info(
            "Serve mode: dashboard available at http://%s:%d/ (source=%s, follow=%s)",
            args.host,
            args.port,
            args.source or "none",
            args.follow,
        )
        print(f"Dashboard: http://{args.host.replace('127.0.0.1', 'localhost')}:{args.port}/")

        def ingest(tick: Dict[str, Any]) -> None:
            apply_tick_to_metrics(metrics, tick)

        if args.source:
            source_path = Path(args.source).expanduser().resolve()

            def worker_target() -> None:
                stream_metrics_file(
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
            ctx.logger.info("Shutting down serve mode")
        finally:
            stop_server()
        return int(Exit.OK)

    return handler


def _configure_compact_snapshot(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--in", dest="infile", required=True)
    parser.add_argument("--out", dest="outfile", required=True)
    parser.add_argument("--compress", action="store_true")

    def handler(args: argparse.Namespace) -> int:
        rh_cls = ctx.robinhood_cls
        try:
            rh = rh_cls.load(args.infile)
        except FileNotFoundError as exc:
            raise IOErrorEnvelope(str(exc)) from exc
        before_size = len(rh)
        before_cap = rh._cap
        before_tombstone = rh.tombstone_ratio()
        ctx.logger.info(
            "Loaded RobinHoodMap snapshot cap=%d size=%d tombstones≈%.2f%%",
            rh._cap,
            len(rh),
            rh.tombstone_ratio() * 100.0,
        )
        rh.compact()
        after_size = len(rh)
        after_tombstone = rh.tombstone_ratio()
        try:
            atomic_map_save(rh, Path(args.outfile), compress=args.compress)
        except OSError as exc:
            raise IOErrorEnvelope(str(exc)) from exc
        ctx.logger.info(
            "Wrote compacted snapshot: %s cap=%d size=%d tombstones≈%.2f%%",
            args.outfile,
            rh._cap,
            len(rh),
            rh.tombstone_ratio() * 100.0,
        )
        ctx.emit_success(
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

    return handler


def _configure_verify_snapshot(parser: argparse.ArgumentParser, ctx: CLIContext) -> Callable[[argparse.Namespace], int]:
    parser.add_argument("--in", dest="infile", required=True)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--repair", action="store_true", help="Attempt safe repair (RobinHood compaction).")
    parser.add_argument("--out", dest="outfile", default=None, help="Write repaired snapshot to this path (default: overwrite input)")

    def handler(args: argparse.Namespace) -> int:
        if ctx.json_enabled():
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                rc = ctx.verify_snapshot(
                    args.infile,
                    verbose=args.verbose,
                    repair=args.repair,
                    repair_out=args.outfile,
                )
            if rc != 0:
                raise InvariantError("Snapshot verification failed")
            messages = [line for line in buffer.getvalue().splitlines() if line.strip()]
            ctx.emit_success(
                "verify-snapshot",
                data={
                    "infile": args.infile,
                    "repaired": bool(args.repair),
                    "messages": messages,
                },
            )
            return int(Exit.OK)

        rc = ctx.verify_snapshot(args.infile, verbose=args.verbose, repair=args.repair, repair_out=args.outfile)
        if rc != 0:
            raise InvariantError("Snapshot verification failed")
        ctx.emit_success(
            "verify-snapshot",
            data={"infile": args.infile, "repaired": bool(args.repair)},
        )
        return int(Exit.OK)

    return handler


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


__all__ = ["CLIContext", "register_subcommands"]
