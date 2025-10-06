from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Dict

import pytest

from adhash.cli.commands import CLIContext, _configure_run_csv
from adhash.workloads import WorkloadDNAResult
from adhash.contracts.error import BadInputError
from adhash.core.maps import RobinHoodMap
from hashmap_cli import run_csv


def _write_minimal_workload(path: Path) -> None:
    path.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")


def _make_cli_context(captured: Dict[str, Any]) -> CLIContext:
    logger = logging.getLogger("test-cli")

    dummy_dna = WorkloadDNAResult(
        schema="adhash.workload.dna/1",
        csv_path="dummy.csv",
        file_size_bytes=None,
        total_rows=0,
        op_counts={},
        op_mix={},
        mutation_fraction=0.0,
        unique_keys_estimated=0,
        key_space_depth=0.0,
        key_length_stats={},
        value_size_stats={},
        key_entropy_bits=0.0,
        key_entropy_normalised=0.0,
        hot_keys=(),
        coverage_targets={},
        numeric_key_fraction=0.0,
        sequential_numeric_step_fraction=0.0,
        adjacent_duplicate_fraction=0.0,
        hash_collision_hotspots={},
        bucket_counts=(),
        bucket_percentiles={},
        collision_depth_histogram={},
        non_empty_buckets=0,
        max_bucket_depth=0,
    )

    def emit_success(command: str, **payload: Any) -> None:
        captured["emit"] = {"command": command, "payload": payload}

    def run_csv_stub(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        captured["run_csv"] = {"args": args, "kwargs": kwargs}
        return {"status": "ok"}

    def analyze_workload_stub(
        csv_path: str, top_keys: int, max_tracked_keys: int
    ) -> WorkloadDNAResult:
        return dummy_dna

    return CLIContext(
        emit_success=emit_success,
        build_map=lambda *a, **k: None,
        run_op=lambda *a, **k: None,
        profile_csv=lambda *a, **k: "adaptive",
        run_csv=run_csv_stub,
        generate_csv=lambda *a, **k: None,
        run_config_wizard=lambda *a, **k: Path("config/config.toml"),
        run_config_editor=lambda *a, **k: {},
        run_ab_compare=lambda *a, **k: {},
        verify_snapshot=lambda *a, **k: 0,
        analyze_workload=analyze_workload_stub,
        invoke_main=lambda *a, **k: 0,
        logger=logger,
        json_enabled=lambda: False,
        robinhood_cls=RobinHoodMap,
        guard=lambda fn: fn,
        latency_bucket_choices=["default"],
    )


def test_run_csv_handler_uses_env_metrics_host_and_port(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "env.csv"
    _write_minimal_workload(csv_path)

    monkeypatch.setenv("ADHASH_METRICS_PORT", "5005")
    monkeypatch.setenv("ADHASH_METRICS_HOST", "0.0.0.0")

    captured: Dict[str, Any] = {}
    ctx = _make_cli_context(captured)

    parser = argparse.ArgumentParser()
    handler = _configure_run_csv(parser, ctx)

    args = parser.parse_args(["--csv", str(csv_path)])
    setattr(args, "mode", "adaptive")

    exit_code = handler(args)
    assert exit_code == 0

    call = captured.get("run_csv", {})
    assert call
    assert call["kwargs"].get("metrics_port") == 5005
    assert call["kwargs"].get("metrics_host") == "0.0.0.0"

    emitted = captured.get("emit", {})
    assert emitted.get("command") == "run-csv"

def test_run_csv_handler_accepts_auto_port_flag(tmp_path) -> None:
    csv_path = tmp_path / "auto.csv"
    _write_minimal_workload(csv_path)

    captured: Dict[str, Any] = {}
    ctx = _make_cli_context(captured)

    parser = argparse.ArgumentParser()
    handler = _configure_run_csv(parser, ctx)

    args = parser.parse_args(["--csv", str(csv_path), "--metrics-port", "auto"])
    setattr(args, "mode", "adaptive")

    exit_code = handler(args)
    assert exit_code == 0

    call = captured.get("run_csv", {})
    assert call
    assert call["kwargs"].get("metrics_port") == 0


def test_run_csv_handler_accepts_auto_port_env(tmp_path, monkeypatch) -> None:
    csv_path = tmp_path / "auto_env.csv"
    _write_minimal_workload(csv_path)

    monkeypatch.setenv("ADHASH_METRICS_PORT", "auto")

    captured: Dict[str, Any] = {}
    ctx = _make_cli_context(captured)

    parser = argparse.ArgumentParser()
    handler = _configure_run_csv(parser, ctx)

    args = parser.parse_args(["--csv", str(csv_path)])
    setattr(args, "mode", "adaptive")

    exit_code = handler(args)
    assert exit_code == 0

    call = captured.get("run_csv", {})
    assert call
    assert call["kwargs"].get("metrics_port") == 0


def test_run_csv_invalid_env_port_raises(monkeypatch, tmp_path) -> None:
    csv_path = tmp_path / "badenv.csv"
    _write_minimal_workload(csv_path)

    monkeypatch.setenv("ADHASH_METRICS_PORT", "not-a-number")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive")
