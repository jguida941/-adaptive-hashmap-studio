"""Module entrypoint for `python -m adhash.mission_control`."""

from __future__ import annotations

import sys

from .app import run_mission_control


def main() -> int:
    return run_mission_control(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
