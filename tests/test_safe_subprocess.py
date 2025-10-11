from __future__ import annotations

import sys
from typing import cast

import pytest

from adhash._safe_subprocess import SubprocessError, safe_popen, safe_run


def test_safe_run_timeout() -> None:
    with pytest.raises(SubprocessError):
        safe_run([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.1)


def test_safe_run_success() -> None:
    result = safe_run([sys.executable, "-c", "print('ok')"])
    assert result.returncode == 0
    assert "ok" in (result.stdout or "")


def test_safe_run_merges_env() -> None:
    result = safe_run(
        [sys.executable, "-c", "import os; print(os.getenv('SAFE_SUBPROC_FLAG'))"],
        env={"SAFE_SUBPROC_FLAG": "demo"},
    )
    assert (result.stdout or "").strip() == "demo"


def test_safe_run_raises_on_failure() -> None:
    with pytest.raises(SubprocessError) as excinfo:
        safe_run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert "exit 3" in str(excinfo.value)


def test_safe_popen_rejects_shell() -> None:
    with pytest.raises(ValueError):
        safe_popen([sys.executable, "--version"], shell=True)  # noqa: S604


def test_safe_popen_rejects_executable_override() -> None:
    with pytest.raises(ValueError):
        safe_popen([sys.executable, "--version"], executable=sys.executable)


def test_safe_run_validates_args_sequence() -> None:
    with pytest.raises(ValueError):
        safe_run(())
    with pytest.raises(ValueError):
        safe_run(["echo", cast(str, 123)])


def test_safe_popen_logs_oserror() -> None:
    bogus = "__nonexistent_executable__"
    with pytest.raises(OSError):
        safe_popen([bogus])
