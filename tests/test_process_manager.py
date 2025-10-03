from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List

import pytest

from adhash.mission_control.process_manager import ProcessManager


@pytest.mark.skipif(sys.platform == "win32", reason="Subprocess commands differ on Windows")
def test_process_manager_runs_and_captures_output(tmp_path: Path) -> None:
    outputs: List[str] = []
    exit_codes: List[int] = []

    manager = ProcessManager(outputs.append, exit_codes.append)
    script = "print('hello world')"
    manager.start([sys.executable, "-c", script])

    # Wait for process to finish
    timeout = time.time() + 5
    while manager.is_running() and time.time() < timeout:
        time.sleep(0.1)

    manager.stop()

    assert any("hello world" in line for line in outputs)
    assert exit_codes and exit_codes[-1] == 0


@pytest.mark.skipif(sys.platform == "win32", reason="Subprocess commands differ on Windows")
def test_process_manager_stop(tmp_path: Path) -> None:
    outputs: List[str] = []
    exit_codes: List[int] = []

    manager = ProcessManager(outputs.append, exit_codes.append)
    script = "import time\ntime.sleep(5)"
    manager.start([sys.executable, "-c", script])
    time.sleep(0.2)
    manager.stop()

    timeout = time.time() + 2
    while manager.is_running() and time.time() < timeout:
        time.sleep(0.1)

    assert not manager.is_running()
