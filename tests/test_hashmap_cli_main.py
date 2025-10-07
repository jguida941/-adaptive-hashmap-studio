from __future__ import annotations

from typing import Any, Dict, List

import pytest

import adhash.hashmap_cli as cli
from adhash.config import AppConfig


def test_main_run_csv_invokes_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: Dict[str, Any] = {}

    def fake_load_app_config(path: str | None) -> AppConfig:
        calls["config_path"] = path
        return AppConfig()

    def fake_set_app_config(cfg: AppConfig) -> None:
        calls["config"] = cfg

    def fake_configure_logging(*args: Any, **kwargs: Any) -> None:
        calls["logging"] = (args, kwargs)

    def fake_run_csv(csv_path: str, mode: str, **kwargs: Any) -> Dict[str, Any]:
        calls["run_csv"] = (csv_path, mode, kwargs)
        return {"summary": {"ops": 1}}

    emissions: List[Dict[str, Any]] = []

    def fake_emit_success(command: str, *, text: str | None = None, data: Dict[str, Any] | None = None) -> None:
        emissions.append({"command": command, "text": text, "data": data or {}})

    monkeypatch.setattr(cli, "load_app_config", fake_load_app_config)
    monkeypatch.setattr(cli, "set_app_config", fake_set_app_config)
    monkeypatch.setattr(cli, "configure_logging", fake_configure_logging)
    monkeypatch.setattr(cli, "run_csv", fake_run_csv)
    monkeypatch.setattr(cli, "emit_success", fake_emit_success)
    monkeypatch.setattr(cli, "OUTPUT_JSON", False, raising=False)

    rc = cli.main([
        "--config",
        "custom.toml",
        "run-csv",
        "--csv",
        "data.csv",
    ])

    assert rc == 0
    assert calls["config_path"] == "custom.toml"
    assert isinstance(calls["config"], AppConfig)
    csv_path, mode, kwargs = calls["run_csv"]
    assert csv_path == "data.csv"
    assert mode == "adaptive"
    assert kwargs["metrics_port"] is None
    assert emissions[-1]["command"] == "run-csv"


def test_main_json_mode_enables_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load_app_config(path: str | None) -> AppConfig:
        return AppConfig()

    monkeypatch.setattr(cli, "load_app_config", fake_load_app_config)
    monkeypatch.setattr(cli, "set_app_config", lambda cfg: None)
    monkeypatch.setattr(cli, "configure_logging", lambda *a, **k: None)
    monkeypatch.setattr(cli, "run_csv", lambda *a, **k: {})
    monkeypatch.setattr(cli, "emit_success", lambda *a, **k: None)
    monkeypatch.setattr(cli, "OUTPUT_JSON", False, raising=False)

    rc = cli.main([
        "--json",
        "run-csv",
        "--csv",
        "data.csv",
    ])

    assert rc == 0
    assert cli.OUTPUT_JSON is True
