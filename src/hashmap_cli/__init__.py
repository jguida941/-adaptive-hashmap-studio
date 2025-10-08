"""Compatibility shim preserving the legacy ``hashmap_cli`` import path."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Iterable

from adhash.hashmap_cli import *  # noqa: F401,F403 - re-export public API by default

_impl = importlib.import_module("adhash.hashmap_cli")
_orig = sys.modules[__name__]


class _Shim(types.ModuleType):
    """Proxy module that mirrors ``adhash.hashmap_cli`` while staying a package."""

    _PROTECTED = {
        "__dict__",
        "__name__",
        "__loader__",
        "__package__",
        "__spec__",
        "__file__",
        "__path__",
        "__doc__",
        "__all__",
    }

    def __getattr__(self, name: str):
        return getattr(_impl, name)

    def __setattr__(self, name: str, value) -> None:
        if name in self._PROTECTED:
            types.ModuleType.__setattr__(self, name, value)
        else:
            setattr(_impl, name, value)

    def __delattr__(self, name: str) -> None:
        if name in self._PROTECTED:
            types.ModuleType.__delattr__(self, name)
        else:
            delattr(_impl, name)

    def __dir__(self) -> list[str]:
        names = set(types.ModuleType.__dir__(self))
        names.update(dir(_impl))
        return sorted(names)


def _assign_meta(shim: _Shim, *, exports: Iterable[str]) -> None:
    module_dir = list(getattr(_orig, "__path__", [str(Path(__file__).parent)]))

    types.ModuleType.__setattr__(shim, "__doc__", getattr(_impl, "__doc__", None))
    types.ModuleType.__setattr__(shim, "__package__", __name__)
    types.ModuleType.__setattr__(
        shim, "__file__", getattr(_orig, "__file__", getattr(_impl, "__file__", __file__))
    )
    types.ModuleType.__setattr__(shim, "__path__", module_dir)
    types.ModuleType.__setattr__(shim, "__loader__", getattr(_orig, "__loader__", None))
    types.ModuleType.__setattr__(shim, "__spec__", getattr(_orig, "__spec__", None))
    types.ModuleType.__setattr__(shim, "__all__", list(exports))


def _resolve_exports() -> list[str]:
    exported = getattr(_impl, "__all__", None)
    if exported is not None:
        return list(exported)
    return [name for name in dir(_impl) if not name.startswith("_")]


_shim = _Shim(__name__)
_assign_meta(_shim, exports=_resolve_exports())

sys.modules[__name__] = _shim
