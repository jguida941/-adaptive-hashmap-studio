#!/usr/bin/env python3
"""Parse mutmut_results.txt and emit structured survivor/timeout summaries.

Usage:
    python tools/mutmut_digest.py [--input PATH] [--output PATH]

Defaults:
    input:  .mutmut-ci/mutmut_results.txt
    output: .mutmut-ci/mutmut_summary.json

The script groups survivors/timeouts by module and by top-level package,
which lets the triage automation focus on the hottest areas first.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable


def parse_mutmut_results(lines: Iterable[str]) -> Dict[str, Dict[str, int]]:
    """Return counters per status for every mutant identifier."""
    status_by_ident: Dict[str, Counter] = defaultdict(Counter)
    for raw in lines:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        ident, status = line.rsplit(":", 1)
        status = status.strip()
        status_by_ident[ident.strip()][status] += 1
    return status_by_ident


def bucketize(status_by_ident: Dict[str, Counter]) -> Dict[str, Dict[str, int]]:
    """Aggregate counts per module bucket."""
    module_counts: Dict[str, Counter] = defaultdict(Counter)
    for ident, counts in status_by_ident.items():
        parts = ident.split(".")
        if not parts:
            continue
        # bucket1: top level (adhash, hashmap_cli, ...)
        top = parts[0]
        module_counts[top].update(counts)
        # bucket2: up to module.submodule
        if len(parts) >= 3:
            sub = ".".join(parts[:3])
            module_counts[sub].update(counts)
        # bucket3: full identifier
        module_counts[ident].update(counts)
    return {module: dict(counter) for module, counter in module_counts.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", default=".mutmut-ci/mutmut_results.txt", help="mutmut results text file"
    )
    parser.add_argument(
        "--output", default=".mutmut-ci/mutmut_summary.json", help="JSON summary output path"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"error: {input_path} not found", file=sys.stderr)
        return 1

    status_by_ident = parse_mutmut_results(input_path.read_text().splitlines())
    module_counts = bucketize(status_by_ident)

    totals = Counter()
    for counts in status_by_ident.values():
        totals.update(counts)

    summary = {
        "totals": dict(totals),
        "modules": module_counts,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote summary to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
