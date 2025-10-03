"""Command-line entry point for the batch benchmark runner."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .runner import BatchRunner, load_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Adaptive Hash Map batch benchmarks from a TOML spec.")
    parser.add_argument("--spec", required=True, help="Path to the TOML batch specification.")
    parser.add_argument(
        "--python",
        default=None,
        help="Optional python executable to use when invoking hashmap_cli.py (defaults to current interpreter).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    spec_path = Path(args.spec).expanduser().resolve()
    spec = load_spec(spec_path)
    runner = BatchRunner(spec=spec, python_executable=args.python)
    runner.run()


if __name__ == "__main__":
    main()
