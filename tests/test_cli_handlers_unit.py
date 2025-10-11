from __future__ import annotations

import argparse
import json
import logging
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from adhash.cli.commands import CLIContext, register_subcommands
from adhash.contracts.error import BadInputError, IOErrorEnvelope
from adhash.core.maps import RobinHoodMap
from adhash.workloads.dna import WorkloadDNAResult


@dataclass
class Recorder:
    run_csv_calls: list[dict[str, Any]] = field(default_factory=list)
    run_config_wizard_calls: list[str] = field(default_factory=list)
    run_config_editor_calls: list[dict[str, Any]] = field(default_factory=list)
    run_ab_compare_calls: list[dict[str, Any]] = field(default_factory=list)
    successes: list[dict[str, Any]] = field(default_factory=list)

    def emit_success(
        self, command: str, *, text: str | None = None, data: dict[str, Any] | None = None
    ) -> None:
        self.successes.append({"command": command, "text": text, "data": data or {}})

    def run_csv(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = {"args": args, "kwargs": kwargs}
        self.run_csv_calls.append(payload)
        return {"ok": True, "args": args, "kwargs": kwargs}

    def run_config_wizard(self, outfile: str) -> Path:
        self.run_config_wizard_calls.append(outfile)
        path = Path(outfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('mode = "adaptive"\n', encoding="utf-8")
        return path

    def run_config_editor(self, infile: str, outfile: str | None, **kwargs: Any) -> dict[str, Any]:
        payload = {"infile": infile, "outfile": outfile, **kwargs}
        self.run_config_editor_calls.append(payload)
        return payload

    def run_ab_compare(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = {"args": args, "kwargs": kwargs}
        self.run_ab_compare_calls.append(payload)
        return {"summary": payload}

    def verify_snapshot(self, _path: str, **_kwargs: Any) -> int:
        return 0


def _dummy_dna() -> WorkloadDNAResult:
    return WorkloadDNAResult(
        schema="adhash.dna.test",
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


CLIParserFactory = Callable[
    [list[str]],
    tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder, CLIContext],
]


@pytest.fixture()
def cli_parser() -> CLIParserFactory:
    def factory(
        argv: list[str],
    ) -> tuple[Callable[[argparse.Namespace], int], argparse.Namespace, Recorder, CLIContext]:
        recorder = Recorder()
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", default="adaptive")
        parser.add_argument("--json", action="store_true")
        subparsers = parser.add_subparsers(dest="cmd", required=True)

        ctx = CLIContext(
            emit_success=recorder.emit_success,
            build_map=lambda mode: {"mode": mode},
            run_op=lambda *_args, **_kwargs: None,
            profile_csv=lambda _path: "adaptive",
            run_csv=recorder.run_csv,
            generate_csv=lambda *_args, **_kwargs: None,
            run_config_wizard=recorder.run_config_wizard,
            run_config_editor=recorder.run_config_editor,
            run_ab_compare=recorder.run_ab_compare,
            verify_snapshot=recorder.verify_snapshot,
            analyze_workload=lambda _path, _top, _max_tracked: _dummy_dna(),
            invoke_main=lambda _argv_inner: 0,
            logger=logging.getLogger("test-cli"),
            json_enabled=lambda: False,
            robinhood_cls=RobinHoodMap,
            guard=lambda fn: fn,
            latency_bucket_choices=["default", "tight"],
        )

        handlers = register_subcommands(subparsers, ctx)
        args = parser.parse_args(argv)
        handler = handlers[args.cmd]
        return handler, args, recorder, ctx

    return factory


def test_profile_requires_csv(cli_parser: CLIParserFactory) -> None:
    with pytest.raises(SystemExit):
        cli_parser(["profile"])


def test_profile_then_invokes_main(cli_parser: CLIParserFactory) -> None:
    handler, args, recorder, ctx = cli_parser(
        [
            "profile",
            "--csv",
            "work.csv",
            "--then",
            "get",
            "demo-key",
        ]
    )
    invoked: list[list[str]] = []

    def fake_invoke(argv: list[str]) -> int:
        invoked.append(list(argv))
        return 0

    object.__setattr__(ctx, "invoke_main", fake_invoke)

    rc = handler(args)

    assert rc == 0
    assert invoked == [["--mode", "adaptive", "get", "demo-key"]]
    payload = recorder.successes[-1]
    assert payload["command"] == "profile"
    assert payload["data"]["recommended_mode"] == "adaptive"


def test_run_csv_handler_uses_env_port(
    monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory, tmp_path: Path
) -> None:
    handler, args, recorder, _ = cli_parser(
        [
            "run-csv",
            "--csv",
            str(tmp_path / "input.csv"),
        ]
    )
    monkeypatch.setenv("ADHASH_METRICS_PORT", "auto")
    handler(args)
    call = recorder.run_csv_calls[-1]
    assert call["kwargs"]["metrics_port"] == 0
    assert call["kwargs"]["metrics_host"] == "127.0.0.1"


def test_run_csv_handler_invalid_port(cli_parser: CLIParserFactory) -> None:
    handler, args, _, _ = cli_parser(
        [
            "run-csv",
            "--csv",
            "work.csv",
            "--metrics-port",
            "invalid",
        ]
    )
    with pytest.raises(BadInputError):
        handler(args)


def test_config_edit_lists_presets(
    _monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory, tmp_path: Path
) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    (preset_dir / "demo.toml").write_text('mode = "adaptive"\n', encoding="utf-8")
    handler, args, recorder, _ = cli_parser(
        [
            "config-edit",
            "--list-presets",
            "--presets-dir",
            str(preset_dir),
        ]
    )
    handler(args)
    assert recorder.run_config_editor_calls == []
    payload = recorder.successes[-1]
    assert payload["command"] == "config-edit"
    assert "demo" in payload["data"].get("presets", [])


def test_config_wizard_invokes_runner(cli_parser: CLIParserFactory, tmp_path: Path) -> None:
    outfile = tmp_path / "generated.toml"
    handler, args, recorder, _ = cli_parser(
        [
            "config-wizard",
            "--outfile",
            str(outfile),
        ]
    )
    handler(args)
    assert outfile.exists()
    assert recorder.run_config_wizard_calls == [str(outfile)]
    assert recorder.successes[-1]["command"] == "config-wizard"


def test_generate_csv_handler_invokes_context(cli_parser: CLIParserFactory, tmp_path: Path) -> None:
    outfile = tmp_path / "out.csv"
    handler, args, recorder, ctx = cli_parser(
        [
            "generate-csv",
            "--outfile",
            str(outfile),
            "--ops",
            "10",
            "--read-ratio",
            "0.7",
            "--key-skew",
            "0.15",
            "--key-space",
            "250",
            "--seed",
            "123",
            "--del-ratio",
            "0.35",
            "--adversarial-ratio",
            "0.05",
            "--adversarial-lowbits",
            "7",
        ]
    )
    captured: dict[str, Any] = {}

    def fake_generate(
        outfile_arg: str,
        ops: int,
        read_ratio: float,
        key_skew: float,
        key_space: int,
        seed: int,
        *,
        del_ratio_within_writes: float,
        adversarial_ratio: float,
        adversarial_lowbits: int,
    ) -> None:
        captured.update(
            {
                "outfile": outfile_arg,
                "ops": ops,
                "read_ratio": read_ratio,
                "key_skew": key_skew,
                "key_space": key_space,
                "seed": seed,
                "del_ratio": del_ratio_within_writes,
                "adversarial_ratio": adversarial_ratio,
                "adversarial_lowbits": adversarial_lowbits,
            }
        )

    object.__setattr__(ctx, "generate_csv", fake_generate)

    rc = handler(args)

    assert rc == 0
    assert captured == {
        "outfile": str(outfile),
        "ops": 10,
        "read_ratio": 0.7,
        "key_skew": 0.15,
        "key_space": 250,
        "seed": 123,
        "del_ratio": 0.35,
        "adversarial_ratio": 0.05,
        "adversarial_lowbits": 7,
    }
    payload = recorder.successes[-1]
    assert payload["command"] == "generate-csv"
    assert payload["data"]["outfile"] == str(outfile)
    assert payload["data"]["ops"] == 10
    assert payload["data"]["read_ratio"] == 0.7
    assert payload["data"]["del_ratio"] == 0.35
    assert payload["data"]["adversarial_lowbits"] == 7


def test_generate_csv_handler_wraps_oserror(cli_parser: CLIParserFactory, tmp_path: Path) -> None:
    handler, args, recorder, ctx = cli_parser(
        [
            "generate-csv",
            "--outfile",
            str(tmp_path / "error.csv"),
        ]
    )

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    object.__setattr__(ctx, "generate_csv", boom)

    with pytest.raises(IOErrorEnvelope, match="disk full"):
        handler(args)

    assert recorder.successes == []


def test_ab_compare_handler_respects_no_artifacts(
    cli_parser: CLIParserFactory, tmp_path: Path
) -> None:
    csv_path = tmp_path / "work.csv"
    csv_path.write_text("op,key,value\nput,K,1\n", encoding="utf-8")
    handler, args, recorder, _ = cli_parser(
        [
            "ab-compare",
            "--csv",
            str(csv_path),
            "--baseline-label",
            "base",
            "--candidate-label",
            "cand",
            "--no-artifacts",
        ]
    )
    handler(args)
    call = recorder.run_ab_compare_calls[-1]
    assert call["kwargs"]["baseline_label"] == "base"
    assert call["kwargs"]["metrics_dir"] is None
    assert recorder.successes[-1]["command"] == "ab-compare"


def test_probe_visualize_put_requires_value(cli_parser: CLIParserFactory) -> None:
    handler, args, _, _ = cli_parser(
        [
            "probe-visualize",
            "--operation",
            "put",
            "--key",
            "K1",
        ]
    )
    with pytest.raises(BadInputError):
        handler(args)


def test_run_csv_handler_metrics_host_env(
    monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory
) -> None:
    handler, args, recorder, _ = cli_parser(
        [
            "run-csv",
            "--csv",
            "work.csv",
        ]
    )
    monkeypatch.setenv("ADHASH_METRICS_HOST", "0.0.0.0")  # noqa: S104
    monkeypatch.setenv("ADHASH_METRICS_PORT", "8088")
    handler(args)
    call = recorder.run_csv_calls[-1]
    assert call["kwargs"]["metrics_host"] == "0.0.0.0"  # noqa: S104
    assert call["kwargs"]["metrics_port"] == 8088


def test_run_csv_handler_env_port_invalid(
    monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory
) -> None:
    handler, args, _, _ = cli_parser(
        [
            "run-csv",
            "--csv",
            "work.csv",
        ]
    )
    monkeypatch.setenv("ADHASH_METRICS_PORT", "invalid")
    with pytest.raises(BadInputError, match="ADHASH_METRICS_PORT"):
        handler(args)


def test_serve_handler_with_compare_and_source(
    monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory, tmp_path: Path
) -> None:
    compare_path = tmp_path / "comparison.json"
    compare_payload = {"summary": {"ops": 10}}
    compare_path.write_text(json.dumps(compare_payload), encoding="utf-8")
    source_path = tmp_path / "metrics.ndjson"
    source_path.write_text("{}", encoding="utf-8")

    start_calls: dict[str, Any] = {}
    stop_called = {"value": False}

    class DummyServer:
        server_port = 4321

    def fake_start(
        _metrics: Any, port: int, *, host: str, comparison: dict[str, Any] | None
    ) -> tuple[DummyServer, Callable[[], None]]:
        start_calls["port"] = port
        start_calls["host"] = host
        start_calls["comparison"] = comparison

        def stop() -> None:
            stop_called["value"] = True

        return DummyServer(), stop

    thread_targets: list[Callable[[], None]] = []

    class DummyThread:
        def __init__(self, target: Callable[[], None], daemon: bool) -> None:
            self._target = target
            self.daemon = daemon
            thread_targets.append(target)

        def start(self) -> None:
            self._target()

    stream_calls: list[dict[str, Any]] = []

    def fake_stream(
        path: Path,
        *,
        follow: bool,
        _callback: Callable[[dict[str, Any]], None],
        poll_interval: float,
    ) -> None:
        stream_calls.append(
            {
                "path": path,
                "follow": follow,
                "poll_interval": poll_interval,
            }
        )

    def fake_sleep(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setenv("ADHASH_METRICS_PORT", "")
    monkeypatch.setattr("adhash.cli.commands.start_metrics_server", fake_start)
    monkeypatch.setattr("adhash.cli.commands.threading.Thread", DummyThread)
    monkeypatch.setattr("adhash.cli.commands.stream_metrics_file", fake_stream)
    monkeypatch.setattr("adhash.cli.commands.time.sleep", fake_sleep)

    handler, args, _, _ctx = cli_parser(
        [
            "serve",
            "--host",
            "0.0.0.0",  # noqa: S104
            "--port",
            "auto",
            "--source",
            str(source_path),
            "--follow",
            "--compare",
            str(compare_path),
            "--poll-interval",
            "0.25",
        ]
    )

    rc = handler(args)
    assert rc == 0
    assert start_calls["port"] == 0
    assert start_calls["host"] == "0.0.0.0"  # noqa: S104
    assert start_calls["comparison"] == compare_payload
    assert stop_called["value"] is True
    assert stream_calls and stream_calls[0]["path"] == source_path.resolve()
    assert stream_calls[0]["follow"] is True
    assert thread_targets, "streaming thread should be created"


def test_serve_handler_compare_missing(cli_parser: CLIParserFactory, tmp_path: Path) -> None:
    handler, args, _, _ = cli_parser(
        [
            "serve",
            "--compare",
            str(tmp_path / "missing.json"),
        ]
    )
    with pytest.raises(IOErrorEnvelope, match="Comparison file not found"):
        handler(args)


def test_serve_handler_invalid_compare_json(cli_parser: CLIParserFactory, tmp_path: Path) -> None:
    bad_compare = tmp_path / "bad.json"
    bad_compare.write_text("{not json}", encoding="utf-8")
    handler, args, _, _ = cli_parser(
        [
            "serve",
            "--compare",
            str(bad_compare),
        ]
    )
    with pytest.raises(IOErrorEnvelope, match="Failed to parse comparison JSON"):
        handler(args)


def test_config_edit_apply_and_save(
    _monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory, tmp_path: Path
) -> None:
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()
    handler, args, recorder, _ = cli_parser(
        [
            "config-edit",
            "--infile",
            str(tmp_path / "in.toml"),
            "--outfile",
            str(tmp_path / "out.toml"),
            "--apply-preset",
            "baseline",
            "--save-preset",
            "new-preset",
            "--presets-dir",
            str(preset_dir),
            "--force",
        ]
    )
    handler(args)
    call = recorder.run_config_editor_calls[-1]
    assert call["infile"] == str(tmp_path / "in.toml")
    assert call["outfile"] == str(tmp_path / "out.toml")
    assert call["apply_preset"] == "baseline"
    assert call["save_preset_name"] == "new-preset"
    assert call["presets_dir"] == str(preset_dir)
    assert call["force"] is True
    assert recorder.successes[-1]["command"] == "config-edit"


def test_mission_control_launches(
    monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory
) -> None:
    fake_module = types.ModuleType("adhash.mission_control.app")
    called: dict[str, Any] = {}

    def fake_run(args: list[str]) -> int:
        called["args"] = args
        return 0

    fake_module.run_mission_control = fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "adhash.mission_control.app", fake_module)
    handler, args, _, _ = cli_parser(["mission-control"])
    rc = handler(args)
    assert rc == 0
    assert called.get("args") == []


def test_compact_snapshot_uses_robinhood_class(
    monkeypatch: pytest.MonkeyPatch, cli_parser: CLIParserFactory, tmp_path: Path
) -> None:
    input_path = tmp_path / "map.snapshot"
    input_path.write_bytes(b"snapshot")
    output_path = tmp_path / "out.snapshot"

    class FakeRobinHood:
        def __init__(self) -> None:
            self._cap = 8
            self._size = 4
            self._tombstones = 0.25
            self._loaded: str | None = None

        @classmethod
        def load(cls, path: str) -> FakeRobinHood:
            instance = cls()
            instance._loaded = path
            return instance

        def __len__(self) -> int:
            return self._size

        def tombstone_ratio(self) -> float:
            return self._tombstones

        def compact(self) -> None:
            self._size = 2
            self._tombstones = 0.1

    saved: dict[str, Any] = {}

    def fake_atomic_save(map_obj: FakeRobinHood, path: Path, *, compress: bool) -> None:
        saved["path"] = path
        saved["compress"] = compress
        saved["cap"] = map_obj._cap
        saved["size"] = len(map_obj)
        saved["tombstones"] = map_obj.tombstone_ratio()

    monkeypatch.setattr("adhash.cli.commands.atomic_map_save", fake_atomic_save)
    handler, args, recorder, ctx = cli_parser(
        [
            "compact-snapshot",
            "--in",
            str(input_path),
            "--out",
            str(output_path),
            "--compress",
        ]
    )
    object.__setattr__(ctx, "robinhood_cls", FakeRobinHood)
    rc = handler(args)
    assert rc == 0
    assert saved["path"] == output_path
    assert saved["compress"] is True
    payload = recorder.successes[-1]
    assert payload["command"] == "compact-snapshot"
    data = payload["data"]
    assert data["infile"] == str(input_path)
    assert data["outfile"] == str(output_path)
    assert data["before"]["size"] == 4
    assert data["after"]["size"] == 2
