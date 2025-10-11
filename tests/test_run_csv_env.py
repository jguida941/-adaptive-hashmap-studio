from __future__ import annotations

import argparse
import gc
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from adhash.cli.commands import CLIContext, _configure_run_csv
from adhash.contracts.error import BadInputError
from adhash.core.maps import RobinHoodMap
from adhash.hashmap_cli import run_csv
from adhash.workloads import WorkloadDNAResult


def _write_minimal_workload(path: Path) -> None:
    path.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")


def _make_cli_context(captured: dict[str, Any]) -> CLIContext:
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

    def run_csv_stub(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured["run_csv"] = {"args": args, "kwargs": kwargs}
        return {"status": "ok"}

    def analyze_workload_stub(
        _csv_path: str, _top_keys: int, _max_tracked_keys: int
    ) -> WorkloadDNAResult:
        return dummy_dna

    return CLIContext(
        emit_success=emit_success,
        build_map=lambda *_args, **_kwargs: None,
        run_op=lambda *_args, **_kwargs: None,
        profile_csv=lambda *_args, **_kwargs: "adaptive",
        run_csv=run_csv_stub,
        generate_csv=lambda *_args, **_kwargs: None,
        run_config_wizard=lambda *_args, **_kwargs: Path("config/config.toml"),
        run_config_editor=lambda *_args, **_kwargs: {},
        run_ab_compare=lambda *_args, **_kwargs: {},
        verify_snapshot=lambda *_args, **_kwargs: 0,
        analyze_workload=analyze_workload_stub,
        invoke_main=lambda *_args, **_kwargs: 0,
        logger=logger,
        json_enabled=lambda: False,
        robinhood_cls=RobinHoodMap,
        guard=lambda fn: fn,
        latency_bucket_choices=["default"],
    )


def test_run_csv_handler_uses_env_metrics_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "env.csv"
    _write_minimal_workload(csv_path)

    monkeypatch.setenv("ADHASH_METRICS_PORT", "5005")
    monkeypatch.setenv("ADHASH_METRICS_HOST", "0.0.0.0")  # noqa: S104

    captured: dict[str, Any] = {}
    ctx = _make_cli_context(captured)

    parser = argparse.ArgumentParser()
    handler = _configure_run_csv(parser, ctx)

    args = parser.parse_args(["--csv", str(csv_path)])
    args.mode = "adaptive"

    exit_code = handler(args)
    assert exit_code == 0

    call = captured.get("run_csv", {})
    assert call
    assert call["kwargs"].get("metrics_port") == 5005
    assert call["kwargs"].get("metrics_host") == "0.0.0.0"  # noqa: S104

    emitted = captured.get("emit", {})
    assert emitted.get("command") == "run-csv"


def test_run_csv_handler_accepts_auto_port_flag(tmp_path: Path) -> None:
    csv_path = tmp_path / "auto.csv"
    _write_minimal_workload(csv_path)

    captured: dict[str, Any] = {}
    ctx = _make_cli_context(captured)

    parser = argparse.ArgumentParser()
    handler = _configure_run_csv(parser, ctx)

    args = parser.parse_args(["--csv", str(csv_path), "--metrics-port", "auto"])
    args.mode = "adaptive"

    exit_code = handler(args)
    assert exit_code == 0

    call = captured.get("run_csv", {})
    assert call
    assert call["kwargs"].get("metrics_port") == 0


def test_run_csv_handler_accepts_auto_port_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "auto_env.csv"
    _write_minimal_workload(csv_path)

    monkeypatch.setenv("ADHASH_METRICS_PORT", "auto")

    captured: dict[str, Any] = {}
    ctx = _make_cli_context(captured)

    parser = argparse.ArgumentParser()
    handler = _configure_run_csv(parser, ctx)

    args = parser.parse_args(["--csv", str(csv_path)])
    args.mode = "adaptive"

    exit_code = handler(args)
    assert exit_code == 0

    call = captured.get("run_csv", {})
    assert call
    assert call["kwargs"].get("metrics_port") == 0


def test_run_csv_invalid_env_port_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_path = tmp_path / "badenv.csv"
    _write_minimal_workload(csv_path)

    monkeypatch.setenv("ADHASH_METRICS_PORT", "not-a-number")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive")


def test_run_csv_cleans_up_resources_on_initial_failure(
    tmp_path: Path, _monkeypatch: pytest.MonkeyPatch, recwarn: pytest.WarningsRecorder
) -> None:
    csv_path = tmp_path / "fail.csv"
    _write_minimal_workload(csv_path)

    metrics_dir = tmp_path / "metrics"

    with pytest.raises(FileNotFoundError):
        run_csv(
            str(csv_path),
            "adaptive",
            metrics_out_dir=str(metrics_dir),
            metrics_port=0,
            snapshot_in=str(metrics_dir / "missing.snapshot"),
        )

    gc.collect()

    assert not [warning for warning in recwarn if warning.category is ResourceWarning]

    ndjson_path = metrics_dir / "metrics.ndjson"
    assert ndjson_path.exists()
    with ndjson_path.open("a", encoding="utf-8") as handle:
        handle.write("")


def test_run_csv_handles_metrics_server_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "perm.csv"
    _write_minimal_workload(csv_path)

    metrics_dir = tmp_path / "perm-metrics"
    summary_path = tmp_path / "perm-summary.json"

    def raise_permission(*_args: Any, **_kwargs: Any) -> tuple[None, None]:
        raise PermissionError("denied")

    monkeypatch.setitem(run_csv.__globals__, "start_metrics_server", raise_permission)

    result = run_csv(
        str(csv_path),
        "adaptive",
        metrics_port=4321,
        metrics_out_dir=str(metrics_dir),
        metrics_max_ticks=2,
        json_summary_out=str(summary_path),
        capture_history=True,
    )

    assert result["status"] == "completed"
    assert result["metrics_port"] == 4321
    assert "metrics_host" not in result
    assert (metrics_dir / "metrics.ndjson").exists()
    assert summary_path.exists()
    assert result["history"]


def test_run_csv_records_metrics_server_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv_path = tmp_path / "server.csv"
    _write_minimal_workload(csv_path)

    metrics_dir = tmp_path / "server-metrics"
    summary_path = tmp_path / "server-summary.json"
    stop_calls: list[str] = []

    class DummyServer:
        server_port = 5050

    def fake_start(_metrics: Any, port: int, host: str) -> tuple[DummyServer, Callable[[], None]]:
        assert port == 0
        assert host == "127.0.0.1"

        def stop() -> None:
            stop_calls.append("stopped")

        return DummyServer(), stop

    monkeypatch.setitem(run_csv.__globals__, "start_metrics_server", fake_start)

    result = run_csv(
        str(csv_path),
        "adaptive",
        metrics_port=0,
        metrics_out_dir=str(metrics_dir),
        metrics_max_ticks=2,
        json_summary_out=str(summary_path),
        capture_history=True,
    )

    assert result["status"] == "completed"
    if stop_calls:
        assert result["metrics_port"] == 5050
        assert stop_calls == ["stopped"]
    else:
        assert result["metrics_port"] != 0
    assert result["metrics_host"] == "127.0.0.1"
    assert "metrics_file" in result
    assert result["history"]
    assert summary_path.exists()


def test_run_csv_full_snapshot_and_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "full.csv"
    csv_path.write_text(
        "op,key,value\nput,K1,1\nput,K2,2\nget,K1,\ndel,K1,\n",
        encoding="utf-8",
    )

    metrics_dir = tmp_path / "full-metrics"
    summary_path = tmp_path / "full-summary.json"
    snapshot_path = tmp_path / "snapshot.dat"
    stop_calls: list[str] = []

    class DummyServer:
        server_port = 4321

    def fake_start(_metrics: Any, port: int, host: str) -> tuple[DummyServer, Callable[[], None]]:
        assert port == 0
        assert host == "127.0.0.1"

        def stop() -> None:
            stop_calls.append("stopped")

        return DummyServer(), stop

    monkeypatch.setitem(run_csv.__globals__, "start_metrics_server", fake_start)

    result = run_csv(
        str(csv_path),
        "fast-lookup",
        metrics_port=0,
        metrics_out_dir=str(metrics_dir),
        metrics_max_ticks=0,
        json_summary_out=str(summary_path),
        snapshot_out=str(snapshot_path),
        compact_interval=0.0,
        latency_sample_every=1,
        capture_history=True,
    )

    assert result["status"] == "completed"
    assert result["metrics_port"] == 4321
    assert result["metrics_host"] == "127.0.0.1"
    assert (metrics_dir / "metrics.ndjson").exists()
    assert summary_path.exists()
    assert snapshot_path.exists()
    assert stop_calls == ["stopped"]


def test_run_csv_with_stubbed_components(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "stub.csv"
    csv_path.write_text("op,key,value\nput,A,1\nget,A,\n", encoding="utf-8")
    metrics_dir = tmp_path / "stub-metrics"
    summary_path = tmp_path / "stub-summary.json"

    class StubMetrics:
        def __init__(self) -> None:
            self.ops_total = 1023
            self.puts_total = 0
            self.gets_total = 0
            self.dels_total = 0
            self.migrations_total = 0
            self.compactions_total = 0
            self.load_factor = 0.0
            self.max_group_len = 0.0
            self.avg_probe_estimate = 0.0
            self.tombstone_ratio = 0.0
            self.backend_name = "hybrid"
            self.alert_flags: dict[str, bool] = {}
            self.active_alerts: list[dict[str, Any]] = []
            self.latency_summary_stats: dict[str, dict[str, float]] = {}
            self.latency_histograms: dict[str, list[tuple[float, int]]] = {}
            self.history_buffer = None
            self.latest_tick: dict[str, Any] | None = None

    class StubSink:
        def __init__(
            self, metrics: StubMetrics, events: list[dict[str, Any]], _clock: Callable[[], float]
        ) -> None:
            self.metrics = metrics
            self.events = events

        def attach(self, _map: Any) -> None:
            return None

        def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
            self.events.append({"type": event_type, **payload})

        def inc_compactions(self) -> None:
            self.metrics.compactions_total += 1

    class StubWatchdog:
        def __init__(self, _policy: Any) -> None:
            self.toggle = False

        def evaluate(self, _tick: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, bool]]:
            self.toggle = not self.toggle
            if self.toggle:
                return ([{"metric": "load_factor", "severity": "warning"}], {"load_factor": True})
            return ([], {"load_factor": False})

    class StubHybrid:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        def put(self, key: str, value: str) -> None:
            self.store[key] = value

        def get(self, key: str) -> str | None:
            return self.store.get(key)

        def delete(self, key: str) -> bool:
            return self.store.pop(key, None) is not None

        def items(self) -> list[tuple[str, str]]:
            return list(self.store.items())

        def trigger_compaction(self) -> bool:
            return True

    def fake_sample_metrics(_map: Any, metrics: StubMetrics) -> None:
        metrics.load_factor = 0.9
        metrics.max_group_len = 3
        metrics.avg_probe_estimate = 2.5
        metrics.tombstone_ratio = 0.1

    class FakeTime:
        def __init__(self) -> None:
            self.value = 0.0

        def perf_counter(self) -> float:
            self.value += 10.0
            return self.value

        def time(self) -> float:
            return self.perf_counter()

    monkeypatch.setitem(run_csv.__globals__, "time", FakeTime())
    monkeypatch.setitem(run_csv.__globals__, "Metrics", StubMetrics)
    monkeypatch.setitem(run_csv.__globals__, "MetricsSink", StubSink)
    monkeypatch.setitem(run_csv.__globals__, "ThresholdWatchdog", StubWatchdog)
    monkeypatch.setitem(run_csv.__globals__, "sample_metrics", fake_sample_metrics)
    monkeypatch.setitem(run_csv.__globals__, "collect_probe_histogram", lambda _m: [[1, 2]])

    def fake_key_heatmap(_map: Any) -> dict[str, Any]:
        return {
            "rows": 1,
            "cols": 1,
            "matrix": [[1]],
            "max": 1,
            "total": 1,
            "slot_span": 1,
            "original_slots": 1,
        }

    monkeypatch.setitem(run_csv.__globals__, "collect_key_heatmap", fake_key_heatmap)
    monkeypatch.setitem(run_csv.__globals__, "build_map", lambda *_args, **_kwargs: StubHybrid())
    monkeypatch.setitem(run_csv.__globals__, "HybridAdaptiveHashMap", StubHybrid)
    monkeypatch.setitem(run_csv.__globals__, "RobinHoodMap", StubHybrid)
    monkeypatch.setitem(run_csv.__globals__, "TwoLevelChainingMap", StubHybrid)

    result = run_csv(
        str(csv_path),
        "adaptive",
        metrics_port=None,
        metrics_out_dir=str(metrics_dir),
        metrics_max_ticks=2,
        json_summary_out=str(summary_path),
        compact_interval=0.0,
        latency_sample_every=1,
        capture_history=True,
    )

    assert result["status"] == "completed"
    assert result["alerts"]
    assert result["compactions_triggered"] >= 1
    assert result["history"]
