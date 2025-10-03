"""Subprocess manager for Mission Control."""

from __future__ import annotations

import shlex
import subprocess
import threading
from typing import Callable, Optional, Sequence


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
            self._proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._thread = threading.Thread(target=self._pump, daemon=True)
            self._thread.start()

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._proc.terminate()
        if self._thread:
            self._thread.join(timeout=2.0)

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
