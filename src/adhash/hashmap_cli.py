"""Backwards-compatibility alias for the Adaptive Hash Map CLI."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, cast


def _import_target() -> object:
    try:
        return import_module("adhash.cli.app")
    except ModuleNotFoundError as exc:  # pragma: no cover - repo-root fallback
        name = getattr(exc, "name", "")
        if name and name != "adhash.cli.app" and not name.startswith("adhash.cli"):
            raise
        root_dir = Path(__file__).resolve().parent
        inspected: list[Path] = []
        found = False
        for candidate in (root_dir.parent, root_dir.parent.parent):
            package_dir = candidate / "adhash"
            inspected.append(package_dir)
            if package_dir.exists():
                sys.path.append(str(candidate))
                found = True
                break
        if not found:
            inspected_str = ", ".join(str(path.parent) for path in inspected)
            raise ImportError(
                "Unable to locate the `adhash` package for CLI fallback. "
                f"Searched in: {inspected_str or 'none'}."
            ) from exc
        return import_module("adhash.cli.app")


if TYPE_CHECKING:  # pragma: no cover - typing helpers
    from adhash.cli.app import *  # noqa: F401,F403

_TARGET = _import_target()
sys.modules[__name__] = cast(ModuleType, _TARGET)


if __name__ == "__main__":  # pragma: no cover - manual invocation
    entry = getattr(_TARGET, "console_main", None)
    if entry is None:
        raise SystemExit("adhash.cli.app.console_main() not found")
    raise SystemExit(entry())
