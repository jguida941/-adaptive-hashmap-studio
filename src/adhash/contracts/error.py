"""Error envelope helpers and exit codes for the Adaptive Hash Map CLI."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from functools import wraps
from typing import Any, NoReturn, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class Exit(IntEnum):
    """Stable exit codes shared across the CLI."""

    OK = 0
    BAD_INPUT = 2
    INVARIANT = 3
    POLICY = 4
    IO = 5


@dataclass(slots=True)
class ErrorEnvelope:
    """Machine-readable error contract for CLI failures."""

    error: str
    detail: str
    hint: str | None = None

    def to_json(self) -> str:
        payload = {"error": self.error, "detail": self.detail}
        if self.hint:
            payload["hint"] = self.hint
        return json.dumps(payload, ensure_ascii=False)


def die(code: Exit, kind: str, detail: str, hint: str | None = None) -> NoReturn:
    """Emit standardized JSON error on stderr and exit with a stable code."""

    env = ErrorEnvelope(error=kind, detail=detail, hint=hint)
    sys.stderr.write(env.to_json() + "\n")
    try:
        sys.stderr.flush()
    finally:
        sys.exit(int(code))


class EnvelopeError(Exception):
    """Base exception that carries an optional hint for the error envelope."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.hint = hint


class BadInputError(EnvelopeError):
    """Raised for malformed user input (CSV schema, flags, etc.)."""


class InvariantError(EnvelopeError):
    """Raised when internal consistency checks fail."""


class PolicyError(EnvelopeError):
    """Raised for unsupported operations or contract violations."""


class IOErrorEnvelope(EnvelopeError):  # noqa: N818 - legacy public API name
    """Raised for IO errors that should map to Exit.IO."""


_EXCEPTION_ORDER: tuple[tuple[type[EnvelopeError], Exit, str], ...] = (
    (BadInputError, Exit.BAD_INPUT, "BadInput"),
    (InvariantError, Exit.INVARIANT, "Invariant"),
    (PolicyError, Exit.POLICY, "Policy"),
    (IOErrorEnvelope, Exit.IO, "IO"),
)


def guard_cli(fn: Callable[..., T]) -> Callable[..., T]:
    """Decorate a CLI handler to enforce exit codes and error envelopes."""

    @wraps(fn)
    def _wrapped(*args: Any, **kwargs: Any) -> T:
        try:
            return fn(*args, **kwargs)
        except EnvelopeError as exc:
            for exc_type, exit_code, label in _EXCEPTION_ORDER:
                if isinstance(exc, exc_type):
                    die(exit_code, label, str(exc), hint=getattr(exc, "hint", None))
            die(Exit.POLICY, "UnhandledEnvelope", str(exc), hint=getattr(exc, "hint", None))
        except FileNotFoundError as exc:
            die(Exit.IO, "FileNotFound", str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unhandled CLI exception")
            die(Exit.POLICY, "Unhandled", f"{type(exc).__name__}: {exc}")

    return _wrapped


__all__ = [
    "Exit",
    "ErrorEnvelope",
    "EnvelopeError",
    "BadInputError",
    "InvariantError",
    "PolicyError",
    "IOErrorEnvelope",
    "guard_cli",
    "die",
]
