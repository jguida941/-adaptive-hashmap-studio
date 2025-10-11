#!/usr/bin/env python3
"""Cross-platform pytest runner used by mutmut.

Ensures required environment variables are present before delegating to pytest.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Prepend the local ``src`` directory to PYTHONPATH and sys.path."""

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    src_dir = (project_root / "src").resolve()
    src_str = str(src_dir)

    existing = os.environ.get("PYTHONPATH")
    if existing:
        paths = existing.split(os.pathsep)
        if src_str not in paths:
            os.environ["PYTHONPATH"] = os.pathsep.join([src_str, *paths])
    else:
        os.environ["PYTHONPATH"] = src_str

    if src_str not in sys.path:
        sys.path.insert(0, src_str)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _ensure_src_on_path()

    try:
        import pytest
    except ImportError as exc:  # pragma: no cover - surfaces during misconfiguration
        raise SystemExit(f"pytest is required for mutmut runner: {exc}") from exc

    args = ["-q", "-m", "not qt", "--ignore=mutants", "--ignore=worktrees", *sys.argv[1:]]
    return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
