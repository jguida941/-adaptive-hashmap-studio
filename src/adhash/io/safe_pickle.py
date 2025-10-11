"""Restricted pickle utilities to protect against arbitrary code execution."""

from __future__ import annotations

import builtins
import io
import pickle  # noqa: S403  # nosec B403 - module is wrapped to restrict globals
from typing import IO, Any

_ALLOWED_BUILTINS = {
    "dict",
    "list",
    "set",
    "frozenset",
    "tuple",
    "str",
    "bytes",
    "bytearray",
    "int",
    "float",
    "complex",
    "bool",
}

_ALLOWED_CLASSES: set[tuple[str, str]] = {
    ("collections", "defaultdict"),
    ("collections", "deque"),
    ("adhash.core.maps", "TwoLevelChainingMap"),
    ("adhash.core.maps", "_Entry"),
    ("adhash.core.maps", "_Tombstone"),
    ("adhash.core.maps", "_RHEntry"),
    ("adhash.core.maps", "RobinHoodMap"),
    ("adhash.core.maps", "HybridAdaptiveHashMap"),
    ("adhash.core.maps", "AdaptiveConfig"),
    ("adhash.core.maps", "MetricsSink"),
    ("adhash.config", "AppConfig"),
    ("adhash.config", "AdaptivePolicy"),
    ("adhash.config", "WatchdogPolicy"),
}


class _RestrictedUnpickler(pickle.Unpickler):  # noqa: S301
    """Pickle loader that only allows a curated set of classes and builtins."""

    def find_class(self, module: str, name: str) -> Any:  # noqa: D401
        if module == "builtins" and name in _ALLOWED_BUILTINS:
            return getattr(builtins, name)
        if (module, name) in _ALLOWED_CLASSES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Disallowed global during snapshot load: {module}.{name}")


def load(file_obj: IO[bytes]) -> Any:
    """Safely unpickle data from ``file_obj`` using a restricted allowlist."""

    return _RestrictedUnpickler(file_obj).load()


def loads(data: bytes) -> Any:
    """Safely unpickle from ``data`` using a restricted allowlist."""

    return load(io.BytesIO(data))


def dump(obj: Any, file_obj: IO[bytes], *, protocol: int = pickle.HIGHEST_PROTOCOL) -> None:
    """Serialize ``obj`` with stdlib pickle, using the requested protocol."""

    pickle.dump(obj, file_obj, protocol=protocol)


def dumps(obj: Any, *, protocol: int = pickle.HIGHEST_PROTOCOL) -> bytes:
    """Serialize ``obj`` to bytes with stdlib pickle."""

    return pickle.dumps(obj, protocol=protocol)


UnpicklingError = pickle.UnpicklingError


__all__ = ["load", "loads", "dump", "dumps", "UnpicklingError"]
