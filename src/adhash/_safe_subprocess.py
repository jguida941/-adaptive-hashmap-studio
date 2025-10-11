"""Safe wrappers for standard-library subprocess functions."""

from __future__ import annotations

import logging
import os
import shlex
import subprocess  # noqa: S404  # nosec B404 - subprocess usage governed via validation helpers
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, cast

logger = logging.getLogger(__name__)

PIPE = subprocess.PIPE
STDOUT = subprocess.STDOUT

_DEFAULT_TIMEOUT = float(os.getenv("ADHASH_SUBPROC_TIMEOUT", "120"))


class SubprocessError(RuntimeError):
    """Raised when a subprocess call times out or exits with a failure status."""


def _merge_env(env: Mapping[str, str] | None) -> MutableMapping[str, str] | None:
    if env is None:
        return None
    merged: dict[str, str] = dict(os.environ)
    merged.update(env)
    return merged


def _validate_args(args: Sequence[str]) -> list[str]:
    if not isinstance(args, list | tuple) or not args:
        raise ValueError("args must be a non-empty sequence of strings")
    if not all(isinstance(arg, str) for arg in args):
        raise ValueError("all subprocess arguments must be strings")
    return list(args)


def _format_command(args: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in args)


def safe_run(
    args: Sequence[str],
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    capture_output: bool = True,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with hardened defaults and helpful error reporting."""

    command = _validate_args(args)
    effective_timeout = _DEFAULT_TIMEOUT if timeout is None else float(timeout)
    cmd_repr = _format_command(command)
    logger.debug("Executing command: %s (timeout=%s)", cmd_repr, effective_timeout)
    try:
        completed = (
            subprocess.run(  # noqa: S603  # nosec B603 - command validated via _validate_args
                command,
                cwd=cwd,
                env=_merge_env(env),
                capture_output=capture_output,
                text=text,
                timeout=effective_timeout,
                check=check,
            )
        )
        if completed.returncode != 0:
            logger.warning(
                "Command exited with code %s: %s\nstdout:\n%s\nstderr:\n%s",
                completed.returncode,
                cmd_repr,
                completed.stdout or "",
                completed.stderr or "",
            )
        else:
            logger.debug("Command succeeded: %s", cmd_repr)
        return completed
    except subprocess.TimeoutExpired as exc:
        logger.warning("Command timed out after %.1fs: %s", effective_timeout, cmd_repr)
        raise SubprocessError(
            f"Command timed out after {effective_timeout:.1f}s: {cmd_repr}"
        ) from exc
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "Command failed (exit %s): %s\nstdout:\n%s\nstderr:\n%s",
            exc.returncode,
            cmd_repr,
            exc.stdout or "",
            exc.stderr or "",
        )
        raise SubprocessError(
            f"Command failed (exit {exc.returncode}): {cmd_repr}\n"
            f"stdout:\n{exc.stdout or ''}\n"
            f"stderr:\n{exc.stderr or ''}"
        ) from exc


def safe_popen(
    args: Sequence[str],
    *,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
    text: bool = True,
    bufsize: int = -1,
    stdout: int | None = PIPE,
    stderr: int | None = PIPE,
    **kwargs: object,
) -> subprocess.Popen[str]:
    """Spawn a subprocess safely for streaming interaction."""

    if "shell" in kwargs:
        raise ValueError("shell-based invocation is not permitted in safe_popen")
    if "executable" in kwargs:
        raise ValueError("Overriding the executable is not permitted in safe_popen")
    command = _validate_args(args)
    cmd_repr = _format_command(command)
    logger.debug("Spawning process: %s", cmd_repr)
    merged_env = _merge_env(env)
    popen_env = cast(Mapping[str, str], merged_env) if merged_env is not None else None
    extra_kwargs = cast(dict[str, Any], dict(kwargs))
    try:
        return cast(
            subprocess.Popen[str],
            subprocess.Popen(  # noqa: S603  # nosec B603 - command validated via _validate_args
                command,
                cwd=cwd,
                env=popen_env,
                text=text,
                bufsize=bufsize,
                stdout=stdout,
                stderr=stderr,
                **extra_kwargs,
            ),
        )
    except OSError as exc:
        logger.error("Failed to spawn process %s: %s", cmd_repr, exc)
        raise


__all__ = [
    "PIPE",
    "STDOUT",
    "SubprocessError",
    "safe_popen",
    "safe_run",
]
