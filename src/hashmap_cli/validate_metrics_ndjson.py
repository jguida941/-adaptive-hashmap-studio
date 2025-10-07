from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except Exception as exc:  # pragma: no cover
    print("jsonschema not installed; install dev extras to validate.", file=sys.stderr)
    raise SystemExit(2) from exc


def _default_schema_text() -> str:
    schema_resource = resources.files("adhash.contracts") / "metrics_schema.json"
    with schema_resource.open(encoding="utf-8") as stream:
        return stream.read()


def _load_schema_text(custom_schema: Path | None) -> str:
    if custom_schema is None:
        return _default_schema_text()
    return custom_schema.read_text(encoding="utf-8")


def _non_monotonic_latency_message(p50: float, p90: float, p99: float, idx: int) -> str:
    return (
        f"[invalid line {idx}] non-monotonic latency percentiles: "
        f"p50={p50}, p90={p90}, p99={p99}"
    )


def _invalid_latency_values_message(values: list[float | int | None], idx: int) -> str:
    return f"[invalid line {idx}] invalid latency values: {values}"


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate metrics NDJSON against metrics.v1 schema",
    )
    parser.add_argument("ndjson", type=Path, help="Path to metrics NDJSON file")
    parser.add_argument(
        "--schema",
        type=Path,
        default=None,
        help="Schema JSON path (default: metrics.v1 bundled schema)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(argv)

    schema = json.loads(_load_schema_text(args.schema))
    validator = Draft202012Validator(schema)

    bad = 0
    for idx, line in enumerate(args.ndjson.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        obj = json.loads(line)
        errors = sorted(validator.iter_errors(obj), key=lambda err: list(err.path))
        if errors:
            bad += 1
            print(f"[invalid line {idx}] {line}", file=sys.stderr)
            for err in errors:
                print(f"  - {err.message} @ {list(err.path)}", file=sys.stderr)
            continue

        lat = obj.get("latency_ms") or obj.get("latency_ns")
        if isinstance(lat, dict):
            overall = lat.get("overall")
            if isinstance(overall, dict):
                raw_values = [overall.get("p50"), overall.get("p90"), overall.get("p99")]
                numeric_values = [v for v in raw_values if isinstance(v, (int, float))]
                if len(numeric_values) == 3 and all(math.isfinite(v) and v >= 0 for v in numeric_values):
                    p50, p90, p99 = numeric_values
                    if not (p50 <= p90 <= p99):
                        bad += 1
                        print(_non_monotonic_latency_message(p50, p90, p99, idx), file=sys.stderr)
                elif any(v is not None for v in raw_values):
                    bad += 1
                    print(_invalid_latency_values_message(raw_values, idx), file=sys.stderr)

    if bad:
        print(f"Validation finished: {bad} invalid line(s)", file=sys.stderr)
    else:
        print("Validation finished: all lines valid")
    return 1 if bad else 0


def console_main() -> int:
    return main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(console_main())
