import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any

import pytest

from adhash.config import AppConfig, AdaptivePolicy
from adhash.metrics import Metrics
from adhash.hashmap_cli import (
    HybridAdaptiveHashMap,
    MetricsSink,
    RobinHoodMap,
    TwoLevelChainingMap,
    build_map,
    configure_logging,
    emit_success,
    logger,
    set_app_config,
)


@pytest.fixture(autouse=True)
def _reset_logging_state():
    handlers = list(logger.handlers)
    yield
    logger.handlers = handlers
    logger.setLevel(logging.INFO)


def test_configure_logging_sets_handlers_and_optionally_rotating(tmp_path: Path):
    log_path = tmp_path / "hashmap.log"
    configure_logging(use_json=True, log_file=str(log_path), max_bytes=1024, backup_count=1)

    assert logger.handlers, "configure_logging should install at least one handler"
    assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)
    assert any(
        isinstance(handler, logging.handlers.RotatingFileHandler) for handler in logger.handlers
    ), "Rotating file handler not installed"

    # log a message and ensure file output exists
    logger.info("hello world")
    configure_logging(use_json=False)
    assert log_path.exists()


def test_emit_success_prints_json_when_enabled(capsys: Any, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("adhash.hashmap_cli.OUTPUT_JSON", True, raising=False)
    emit_success("put", text="ack", data={"key": "alpha"})
    output = capsys.readouterr().out.strip()
    payload = json.loads(output)
    assert payload["ok"] is True
    assert payload["command"] == "put"
    assert payload["result"] == "ack"
    assert payload["key"] == "alpha"


@pytest.mark.parametrize(
    "mode,expected_cls",
    [
        ("fast-insert", TwoLevelChainingMap),
        ("fast-lookup", RobinHoodMap),
        ("memory-tight", RobinHoodMap),
        ("adaptive", HybridAdaptiveHashMap),
    ],
)
def test_build_map_supports_modes(mode: str, expected_cls: type) -> None:
    sink = MetricsSink(Metrics())
    policy = AdaptivePolicy(
        start_backend="chaining",
        initial_buckets=64,
        groups_per_bucket=4,
        initial_capacity_rh=128,
        incremental_batch=16,
        max_lf_chaining=0.8,
        max_group_len=6,
        max_avg_probe_robinhood=8.0,
        max_tombstone_ratio=0.3,
        large_map_warn_threshold=1_000,
    )
    set_app_config(AppConfig(adaptive=policy))

    m = build_map(mode, sink=sink)
    assert isinstance(m, expected_cls)


def test_build_map_rejects_unknown_mode():
    set_app_config(AppConfig())
    with pytest.raises(ValueError):
        build_map("invalid-mode")
