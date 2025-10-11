"""Subprocess manager for Mission Control."""

from __future__ import annotations

import contextlib
import logging
import os
import shlex
import shutil
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from adhash._safe_subprocess import PIPE, STDOUT, safe_popen

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from subprocess import Popen  # noqa: S404  # nosec B404 - type-only import
else:  # pragma: no cover - runtime type hint support
    Popen = Any  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _is_executable(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    if os.name == "nt":
        pathext = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC")
        allowed = {ext.strip().lower() for ext in pathext.split(";") if ext}
        if path.suffix:
            return path.suffix.lower() in allowed
        return os.access(path, os.X_OK)
    return os.access(path, os.X_OK)


class ProcessManager:
    """Launches a subprocess and streams stdout/stderr via callbacks."""

    def __init__(self, on_output: Callable[[str], None], on_exit: Callable[[int], None]) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        self._proc: Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._trusted_executables = self._discover_trusted_executables()

    @staticmethod
    def _discover_trusted_executables() -> set[Path]:
        trusted: set[Path] = set()

        def _register(path_like: str | Path | None, label: str) -> None:
            if not path_like:
                return
            candidate = Path(path_like)
            try:
                resolved = candidate.resolve()
            except (RuntimeError, OSError) as exc:
                logger.warning("Failed to resolve %s (%s): %s", label, candidate, exc)
                return
            if not _is_executable(resolved):
                logger.warning("%s is not an executable file: %s", label, resolved)
                return
            trusted.add(resolved)

        _register(sys.executable, "sys.executable")
        for alias in ("python", "python3"):
            resolved_alias = shutil.which(alias)
            if resolved_alias:
                _register(resolved_alias, alias)
        hashmap_cli = shutil.which("hashmap-cli")
        if hashmap_cli:
            _register(hashmap_cli, "hashmap-cli")
        return trusted

    def _validate_args(self, args: Sequence[str]) -> list[str]:
        if not args:
            raise ValueError("Process command cannot be empty")
        first = args[0]
        candidate = Path(first)
        if not any(sep in first for sep in ("/", "\\")):
            resolved = shutil.which(first)
            if resolved is None:
                raise ValueError(f"Executable '{first}' not found on PATH")
            candidate = Path(resolved)
        try:
            candidate = candidate.resolve()
        except (RuntimeError, OSError) as exc:
            raise ValueError(f"Cannot resolve executable path '{first}': {exc}") from exc
        if candidate not in self._trusted_executables:
            raise ValueError(f"Executable '{candidate}' is not trusted for mission control runs")
        return [str(candidate), *args[1:]]

    def start(self, args: Sequence[str]) -> None:
        try:
            cmd = self._validate_args(args)
        except ValueError as exc:
            logger.error("Rejected process invocation: %s", exc)
            running = False
            with self._lock:
                if self._proc and self._proc.poll() is None:
                    running = True
                else:
                    self._proc = None
                    self._thread = None
            if not running:
                self._notify_start_failure()
            raise
        with self._lock:
            if self._proc and self._proc.poll() is None:
                raise RuntimeError("Process already running")
            failure_exc: OSError | None = None
            try:
                self._proc = safe_popen(
                    cmd,
                    stdout=PIPE,
                    stderr=STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                logger.error("Failed to start process %s: %s", " ".join(cmd), exc)
                self._proc = None
                self._thread = None
                failure_exc = exc
            else:
                self._thread = threading.Thread(target=self._pump, daemon=True)
                self._thread.start()
        if failure_exc is not None:
            self._notify_start_failure()
            raise RuntimeError(f"Failed to start process: {failure_exc}") from failure_exc

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        thread = self._thread
        if thread:
            thread.join(timeout=2.0)
            if thread.is_alive():
                logger.warning("Process thread did not terminate cleanly")
            with self._lock:
                if self._thread is thread:
                    self._thread = None

    def _pump(self) -> None:
        proc = self._proc
        if proc is None:
            logger.debug("Process pump invoked with no active process")
            return
        stdout = proc.stdout
        if stdout is None:
            logger.debug("Process %s has no stdout to read", proc.pid)
            code = proc.wait()
            self._on_exit(code)
            with self._lock:
                self._proc = None
                self._thread = None
            return
        try:
            for line in stdout:
                self._on_output(line.rstrip())
        finally:
            code = proc.wait()
            with contextlib.suppress(Exception):
                if proc.stdout:
                    proc.stdout.close()
            self._on_exit(code)
            with self._lock:
                self._proc = None
                self._thread = None

    def _notify_start_failure(self) -> None:
        with contextlib.suppress(Exception):
            self._on_exit(-1)

    @staticmethod
    def parse_command(command: str) -> Sequence[str]:
        return shlex.split(command)
