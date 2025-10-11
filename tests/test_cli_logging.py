from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from adhash.cli import app


def test_extend_sys_path_executes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_root = tmp_path / "pkg"
    fake_root.mkdir()
    (fake_root / "adhash").mkdir()
    monkeypatch.setattr(app, "ROOT_DIR", fake_root / "adhash" / "cli")
    monkeypatch.setattr(sys, "path", [])
    app._extend_sys_path()
    assert sys.path and sys.path[0] == str(fake_root)


def test_json_formatter_with_exc_and_stack() -> None:
    formatter = app.JsonFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        record = logging.getLogger("test").makeRecord(
            "test", logging.ERROR, __file__, 0, "failure", (), sys.exc_info(), func="func"
        )
    record.stack_info = "trace info"
    payload = json.loads(formatter.format(record))
    assert payload["level"] == "ERROR"
    assert "exc_info" in payload
    assert payload["stack"]


def test_configure_logging_json_and_file(tmp_path: Path) -> None:
    log_file = tmp_path / "app.log"
    app.configure_logging(use_json=True, log_file=str(log_file))
    logger = logging.getLogger("hashmap_cli")
    logger.error("error message")
    # handlers should include stream + rotating file
    assert any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers)
    assert log_file.exists()


def test_emit_success_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(app, "OUTPUT_JSON", True)
    app.emit_success("demo", text="done", data={"value": 5})
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "demo"
    assert payload["value"] == 5
    assert payload["result"] == "done"
    monkeypatch.setattr(app, "OUTPUT_JSON", False)
