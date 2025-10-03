from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
except Exception as exc:  # pragma: no cover
    print("jsonschema not installed; install dev extras to validate.", file=sys.stderr)
    raise SystemExit(2) from exc


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SCHEMA = SCRIPT_DIR.parent / "src/adhash/contracts/metrics_schema.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate metrics NDJSON against metrics.v1 schema")
    parser.add_argument("ndjson", type=Path, help="Path to metrics NDJSON file")
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help="Schema JSON path (default: metrics.v1)",
    )
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
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
                        print(
                            f"[invalid line {idx}] non-monotonic latency percentiles: "
                            f"p50={p50}, p90={p90}, p99={p99}",
                            file=sys.stderr,
                        )
                elif any(v is not None for v in raw_values):
                    bad += 1
                    print(f"[invalid line {idx}] invalid latency values: {raw_values}", file=sys.stderr)
    if bad:
        print(f"Validation finished: {bad} invalid line(s)", file=sys.stderr)
    else:
        print("Validation finished: all lines valid")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())