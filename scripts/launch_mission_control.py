"""Launch Adaptive Hash Map Mission Control without typing the full CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    os.chdir(repo_root)
    try:
        from adhash.mission_control import run_mission_control
    except ModuleNotFoundError as exc:  # PyQt6 or package missing
        missing = exc.name or "dependency"
        message = (
            f"Mission Control dependency '{missing}' is missing. Install with pip install '.[gui]'."
        )
        print(message, file=sys.stderr)
        return 2
    except (ImportError, RuntimeError) as exc:
        print(f"Failed to import Mission Control: {exc}", file=sys.stderr)
        return 1

    try:
        return run_mission_control(sys.argv[1:])
    except (RuntimeError, OSError) as exc:
        print(f"Mission Control exited with an error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
