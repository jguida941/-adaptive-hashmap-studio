"""Adaptive Hash Map CLI package."""

from . import app as _app
from . import commands as _commands

__all__ = []

for _mod in (_app, _commands):
    for _name in getattr(_mod, "__all__", dir(_mod)):
        if _name.startswith("_"):
            continue
        globals()[_name] = getattr(_mod, _name)
        if _name not in __all__:
            __all__.append(_name)

del _mod, _name
