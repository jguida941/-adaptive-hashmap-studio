from __future__ import annotations

import json
import os
import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

from adhash.cli.commands import CLIContext, register_subcommands
from adhash.contracts.error import BadInputError, IOErrorEnvelope
from adhash.core.maps import RobinHoodMap
from adhash.workloads.dna import WorkloadDNAResult


@dataclass
class Recorder:
    run_csv_calls: List[Dict[str, Any]] = field(default_factory=list)
    run_config_wizard_calls: List[str] = field(default_factory=list)
    run_config_editor_calls: List[Dict[str, Any]] = field(default_factory=list)
    run_ab_compare_calls: List[Dict[str, Any]] = field(default_factory=list)
    successes: List[Dict[str, Any]] = field(default_factory=list)

    def emit_success(self, command: str, *, text: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.successes.append({"command": command, "text": text, "data": data or {}})

    def run_csv(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        payload = {"args": args, "kwargs": kwargs}
        self.run_csv_calls.append(payload)
        return {"ok": True, "args": args, "kwargs": kwargs}

    def run_config_wizard(self, outfile: str) -> Path:
        self.run_config_wizard_calls.append(outfile)
        path = Path(outfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("mode = \"adaptive\"\n", encoding="utf-8")
        return path

    def run_config_editor(self, infile: str, outfile: Optional[str], **kwargs: Any) -> Dict[str, Any]:
        payload = {"infile": infile, "outfile": outfile, **kwargs}
        self.run_config_editor_calls.append(payload)
        return payload

    def run_ab_compare(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        payload = {"args": args, "kwargs": kwargs}
        self.run_ab_compare_calls.append(payload)
        return {"summary": payload}

    def verify_snapshot(self, _path: str, **kwargs: Any) -> int:
        return 0


def _dummy_dna() -> WorkloadDNAResult:
    return WorkloadDNAResult(
        schema="adhash.dna.test",
        csv_path="/tmp/dummy.csv",
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


@pytest.fixture()
def cli_parser(tmp_path: Path) -> Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]]:
    def factory(argv: List[str]) -> tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]:
        recorder = Recorder()
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", default="adaptive")
        parser.add_argument("--json", action="store_true")
        subparsers = parser.add_subparsers(dest="cmd", required=True)

        ctx = CLIContext(
            emit_success=recorder.emit_success,
            build_map=lambda mode: {"mode": mode},
            run_op=lambda *args, **kwargs: None,
            profile_csv=lambda path: "adaptive",
            run_csv=recorder.run_csv,
            generate_csv=lambda *args, **kwargs: None,
            run_config_wizard=recorder.run_config_wizard,
            run_config_editor=recorder.run_config_editor,
            run_ab_compare=recorder.run_ab_compare,
            verify_snapshot=recorder.verify_snapshot,
            analyze_workload=lambda path, top, max_tracked: _dummy_dna(),
            invoke_main=lambda argv_inner: 0,
            logger=logging.getLogger("test-cli"),
            json_enabled=lambda: False,
            robinhood_cls=RobinHoodMap,
            guard=lambda fn: fn,
            latency_bucket_choices=["default", "tight"],
        )

        handlers = register_subcommands(subparsers, ctx)
        args = parser.parse_args(argv)
        handler = handlers[args.cmd]
        return handler, args, recorder

    return factory


def test_run_csv_handler_uses_env_port(monkeypatch: pytest.MonkeyPatch, cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    handler, args, recorder = cli_parser([
        "run-csv",
        "--csv",
        str(tmp_path / "input.csv"),
    ])
    monkeypatch.setenv("ADHASH_METRICS_PORT", "auto")
    handler(args)
    call = recorder.run_csv_calls[-1]
    assert call["kwargs"]["metrics_port"] == 0
    assert call["kwargs"]["metrics_host"] == "127.0.0.1"


def test_run_csv_handler_invalid_port(cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]]) -> None:
    handler, args, _ = cli_parser([
        "run-csv",
        "--csv",
        "work.csv",
        "--metrics-port",
        "invalid",
    ])
    with pytest.raises(BadInputError):
        handler(args)


def test_config_edit_lists_presets(monkeypatch: pytest.MonkeyPatch, cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    (preset_dir / "demo.toml").write_text("mode = \"adaptive\"\n", encoding="utf-8")
    handler, args, recorder = cli_parser([
        "config-edit",
        "--list-presets",
        "--presets-dir",
        str(preset_dir),
    ])
    handler(args)
    assert recorder.run_config_editor_calls == []
    payload = recorder.successes[-1]
    assert payload["command"] == "config-edit"
    assert "demo" in payload["data"].get("presets", [])


def test_config_wizard_invokes_runner(cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    outfile = tmp_path / "generated.toml"
    handler, args, recorder = cli_parser([
        "config-wizard",
        "--outfile",
        str(outfile),
    ])
    handler(args)
    assert outfile.exists()
    assert recorder.run_config_wizard_calls == [str(outfile)]
    assert recorder.successes[-1]["command"] == "config-wizard"


def test_ab_compare_handler_respects_no_artifacts(cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    csv_path = tmp_path / "work.csv"
    csv_path.write_text("op,key,value\nput,K,1\n", encoding="utf-8")
    handler, args, recorder = cli_parser([
        "ab-compare",
        "--csv",
        str(csv_path),
        "--baseline-label",
        "base",
        "--candidate-label",
        "cand",
        "--no-artifacts",
    ])
    handler(args)
    call = recorder.run_ab_compare_calls[-1]
    assert call["kwargs"]["baseline_label"] == "base"
    assert call["kwargs"]["metrics_dir"] is None
    assert recorder.successes[-1]["command"] == "ab-compare"


def test_probe_visualize_put_requires_value(cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]]) -> None:
    handler, args, _ = cli_parser([
        "probe-visualize",
        "--operation",
        "put",
        "--key",
        "K1",
    ])
    with pytest.raises(BadInputError):
        handler(args)


def test_run_csv_handler_metrics_host_env(monkeypatch: pytest.MonkeyPatch, cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]]) -> None:
    handler, args, recorder = cli_parser([
        "run-csv",
        "--csv",
        "work.csv",
    ])
    monkeypatch.setenv("ADHASH_METRICS_HOST", "0.0.0.0")
    monkeypatch.setenv("ADHASH_METRICS_PORT", "8088")
    handler(args)
    call = recorder.run_csv_calls[-1]
    assert call["kwargs"]["metrics_host"] == "0.0.0.0"
    assert call["kwargs"]["metrics_port"] == 8088


def test_run_csv_handler_env_port_invalid(monkeypatch: pytest.MonkeyPatch, cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]]) -> None:
    handler, args, _ = cli_parser([
        "run-csv",
        "--csv",
        "work.csv",
    ])
    monkeypatch.setenv("ADHASH_METRICS_PORT", "invalid")
    with pytest.raises(BadInputError, match="ADHASH_METRICS_PORT"):
        handler(args)


def test_serve_handler_with_compare_and_source(monkeypatch: pytest.MonkeyPatch, cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    compare_path = tmp_path / "comparison.json"
    compare_payload = {"summary": {"ops": 10}}
    compare_path.write_text(json.dumps(compare_payload), encoding="utf-8")
    source_path = tmp_path / "metrics.ndjson"
    source_path.write_text("{}", encoding="utf-8")

    start_calls: Dict[str, Any] = {}
    stop_called = {"value": False}

    class DummyServer:
        server_port = 4321

    def fake_start(metrics: Any, port: int, *, host: str, comparison: Optional[Dict[str, Any]]) -> tuple[DummyServer, Callable[[], None]]:
        start_calls["port"] = port
        start_calls["host"] = host
        start_calls["comparison"] = comparison

        def stop() -> None:
            stop_called["value"] = True

        return DummyServer(), stop

    thread_targets: List[Callable[[], None]] = []

    class DummyThread:
        def __init__(self, target: Callable[[], None], daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            thread_targets.append(target)

        def start(self) -> None:
            self._target()

    stream_calls: List[Dict[str, Any]] = []

    def fake_stream(path: Path, *, follow: bool, callback: Callable[[Dict[str, Any]], None], poll_interval: float) -> None:
        stream_calls.append({
            "path": path,
            "follow": follow,
            "poll_interval": poll_interval,
        })

    def fake_sleep(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setenv("ADHASH_METRICS_PORT", "")
    monkeypatch.setattr("adhash.cli.commands.start_metrics_server", fake_start)
    monkeypatch.setattr("adhash.cli.commands.threading.Thread", DummyThread)
    monkeypatch.setattr("adhash.cli.commands.stream_metrics_file", fake_stream)
    monkeypatch.setattr("adhash.cli.commands.time.sleep", fake_sleep)

    handler, args, _ = cli_parser([
        "serve",
        "--host",
        "0.0.0.0",
        "--port",
        "auto",
        "--source",
        str(source_path),
        "--follow",
        "--compare",
        str(compare_path),
        "--poll-interval",
        "0.25",
    ])

    rc = handler(args)
    assert rc == 0
    assert start_calls["port"] == 0
    assert start_calls["host"] == "0.0.0.0"
    assert start_calls["comparison"] == compare_payload
    assert stop_called["value"] is True
    assert stream_calls and stream_calls[0]["path"] == source_path.resolve()
    assert stream_calls[0]["follow"] is True
    assert thread_targets, "streaming thread should be created"


def test_serve_handler_compare_missing(cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    handler, args, _ = cli_parser([
        "serve",
        "--compare",
        str(tmp_path / "missing.json"),
    ])
    with pytest.raises(IOErrorEnvelope, match="Comparison file not found"):
        handler(args)


def test_serve_handler_invalid_compare_json(cli_parser: Callable[[List[str]], tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder]], tmp_path: Path) -> None:
    bad_compare = tmp_path / "bad.json"
    bad_compare.write_text("{not json}", encoding="utf-8")
    handler, args, _ = cli_parser([
        "serve",
        "--compare",
        str(bad_compare),
    ])
    with pytest.raises(IOErrorEnvelope, match="Failed to parse comparison JSON"):
        handler(args)
