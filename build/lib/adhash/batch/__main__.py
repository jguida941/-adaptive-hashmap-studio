"""Command-line entry point for the batch benchmark runner."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .runner import BatchRunner, load_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Adaptive Hash Map batch benchmarks from a TOML spec.")
    parser.add_argument("--spec", help="Path to the TOML batch specification.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available specification files bundled with the project (no execution).",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Optional python executable to use when invoking hashmap_cli.py (defaults to current interpreter).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    if args.list:
        _list_specs()
        return
    if not args.spec:
        raise SystemExit("--spec is required unless --list is provided")

    spec_path = Path(args.spec).expanduser().resolve()
    spec = load_spec(spec_path)
    runner = BatchRunner(spec=spec, python_executable=args.python)
    runner.run()


def _list_specs() -> None:
    from pathlib import Path

    this_file = Path(__file__).resolve()
    repo_root = this_file.parents[3]
    search_dirs = [
        repo_root / "docs" / "examples",
        this_file.parent / "examples",
    ]

    seen: set[Path] = set()
    specs: list[Path] = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        for candidate in sorted(directory.glob("*.toml")):
            if candidate not in seen:
                seen.add(candidate)
                try:
                    rel = candidate.relative_to(repo_root)
                except ValueError:
                    rel = candidate
                specs.append(rel)

    if not specs:
        print("No batch specifications found.")
        return

    print("Available batch specifications:\n")
    for spec in specs:
        print(f"  - {spec}")


if __name__ == "__main__":
    main()
