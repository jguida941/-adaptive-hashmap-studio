"""Convenience launcher for the Adaptive Hash Map Textual TUI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)
    try:
        from adhash.tui.__main__ import build_parser  # type: ignore
        from adhash.tui.app import run_tui  # type: ignore
    except ModuleNotFoundError as exc:
        missing = exc.name or "dependency"
        print(
            f"TUI dependency '{missing}' is missing. Install with pip install '.[ui]'.",
            file=sys.stderr,
        )
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to import TUI modules: {exc}", file=sys.stderr)
        return 1

    parser = build_parser()
    args = parser.parse_args()
    try:
        run_tui(
            metrics_endpoint=args.metrics_endpoint,
            history_endpoint=args.history_endpoint,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"TUI exited with an error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
