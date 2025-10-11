"""Subcommand registration helpers for the Adaptive Hash Map CLI."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import TYPE_CHECKING

from . import base as base_module
from .base import CLIContext, register_subcommands  # noqa: F401

if TYPE_CHECKING:  # pragma: no cover - typing helpers
    from .base import (
        Exit,
        _configure_ab_compare,
        _configure_compact_snapshot,
        _configure_config_edit,
        _configure_config_wizard,
        _configure_del,
        _configure_generate,
        _configure_get,
        _configure_inspect_snapshot,
        _configure_items,
        _configure_mission_control,
        _configure_probe_visualize,
        _configure_profile,
        _configure_put,
        _configure_run_csv,
        _configure_serve,
        _configure_verify_snapshot,
        _configure_workload_dna,
    )

    _TYPE_CHECK_USAGE = (
        Exit,
        _configure_ab_compare,
        _configure_compact_snapshot,
        _configure_config_edit,
        _configure_config_wizard,
        _configure_del,
        _configure_generate,
        _configure_get,
        _configure_inspect_snapshot,
        _configure_items,
        _configure_mission_control,
        _configure_probe_visualize,
        _configure_profile,
        _configure_put,
        _configure_run_csv,
        _configure_serve,
        _configure_verify_snapshot,
        _configure_workload_dna,
    )

__all__ = list(dict.fromkeys(getattr(base_module, "__all__", [])))
for _export in ("CLIContext", "register_subcommands"):
    if _export not in __all__:
        __all__.append(_export)


class _CLICommandsModule(ModuleType):
    """Proxy module that forwards attribute access and mutation to `base`."""

    def __getattr__(self, name: str) -> object:  # pragma: no cover - simple delegation
        return getattr(base_module, name)

    def __setattr__(self, name: str, value: object) -> None:  # pragma: no cover - delegation
        if not name.startswith("__"):
            setattr(base_module, name, value)
            return
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:  # pragma: no cover - delegation
        if not name.startswith("__") and hasattr(base_module, name):
            delattr(base_module, name)
            if name in self.__dict__:
                super().__delattr__(name)
            return
        super().__delattr__(name)

    def __dir__(self) -> list[str]:  # pragma: no cover - simple combination
        combined = set(super().__dir__())
        combined.update(dir(base_module))
        return sorted(combined)


_module = sys.modules[__name__]
_module.__class__ = _CLICommandsModule

for _name in dir(base_module):
    if not _name.startswith("_") and _name not in __all__:
        __all__.append(_name)

del _module, _CLICommandsModule
if "_name" in locals():
    del _name
