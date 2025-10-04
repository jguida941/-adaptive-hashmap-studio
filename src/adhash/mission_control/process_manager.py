"""Subprocess manager for Mission Control."""

from __future__ import annotations

import logging
import shlex
import subprocess
import threading
from typing import Callable, Optional, Sequence


logger = logging.getLogger(__name__)


class ProcessManager:
    """Launches a subprocess and streams stdout/stderr via callbacks."""

    def __init__(self, on_output: Callable[[str], None], on_exit: Callable[[int], None]) -> None:
        self._on_output = on_output
        self._on_exit = on_exit
        self._proc: Optional[subprocess.Popen[str]] = None
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self, args: Sequence[str]) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                raise RuntimeError("Process already running")
            try:
                self._proc = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                logger.error("Failed to start process %s: %s", " ".join(args), exc)
                self._proc = None
                self._thread = None
                self._on_exit(-1)
                raise RuntimeError(f"Failed to start process: {exc}") from exc
            self._thread = threading.Thread(target=self._pump, daemon=True)
            self._thread.start()

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
        assert self._proc is not None
        proc = self._proc
        try:
            assert proc.stdout is not None
            stdout = proc.stdout
            for line in stdout:
                self._on_output(line.rstrip())
        finally:
            code = proc.wait()
            self._on_exit(code)
            with self._lock:
                self._proc = None
                self._thread = None

    @staticmethod
    def parse_command(command: str) -> Sequence[str]:
        return shlex.split(command)
