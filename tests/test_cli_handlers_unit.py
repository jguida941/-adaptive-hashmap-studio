from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

from adhash.cli.commands import CLIContext, register_subcommands
from adhash.contracts.error import BadInputError


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
            analyze_workload=lambda path, top, max_tracked: None,
            invoke_main=lambda argv_inner: 0,
            logger=None,  # type: ignore[arg-type]
            json_enabled=lambda: False,
            robinhood_cls=None,  # type: ignore[arg-type]
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
