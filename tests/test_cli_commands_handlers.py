from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

import pytest

from adhash.cli import commands

from tests.test_cli_commands_register import _SentinelGuard, _build_cli_context


@dataclass
class _RecordingHooks:
    ab_args: Optional[Dict[str, Any]] = None
    emitted: Optional[Dict[str, Any]] = None

    def run_ab_compare(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        self.ab_args = {
            "args": args,
            "kwargs": kwargs,
        }
        return {"status": "ok", "kwargs": kwargs}

    def emit_success(self, *_args: Any, **kwargs: Any) -> None:
        self.emitted = kwargs


@dataclass
class _BasicHooks:
    next_output: Optional[str] = None
    profile_return: str = "hybrid"
    build_modes: List[str] = None  # type: ignore[assignment]
    run_calls: List[Tuple[Any, str, Optional[str], Optional[str]]] = None  # type: ignore[assignment]
    profile_args: List[str] = None  # type: ignore[assignment]
    emitted: Optional[Dict[str, Any]] = None
    invoked: Optional[List[str]] = None

    def __post_init__(self) -> None:
        self.build_modes = []
        self.run_calls = []
        self.profile_args = []

    def build_map(self, mode: str) -> Any:
        self.build_modes.append(mode)
        return {"mode": mode}

    def run_op(
        self, map_obj: Any, op: str, key: Optional[str], value: Optional[str]
    ) -> Optional[str]:
        self.run_calls.append((map_obj, op, key, value))
        return self.next_output

    def emit_success(self, command: str, **kwargs: Any) -> None:
        self.emitted = {"command": command, **kwargs}

    def profile_csv(self, path: str) -> str:
        self.profile_args.append(path)
        return self.profile_return

    def invoke_main(self, argv: List[str]) -> int:
        self.invoked = argv
        return 0


def _invoke(
    handler_factory: Any, parser: argparse.ArgumentParser, argv: list[str]
) -> _RecordingHooks:
    hooks = _RecordingHooks()
    guard = _SentinelGuard()
    ctx = _build_cli_context(
        guard,
        run_ab_compare=hooks.run_ab_compare,
        emit_success=hooks.emit_success,
    )
    handler = handler_factory(parser, ctx)
    args = parser.parse_args(argv)
    handler(args)
    return hooks


def test_configure_ab_compare_invokes_context_with_expected_kwargs(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli ab-compare")
    handler_factory = commands._configure_ab_compare

    csv_path = tmp_path / "workload.csv"
    csv_path.write_text("header\n", encoding="utf-8")

    out_dir = tmp_path / "out"

    hooks = _invoke(
        handler_factory,
        parser,
        [
            "--csv",
            csv_path.as_posix(),
            "--baseline-label",
            "baseline run",
            "--candidate-label",
            "candidate run",
            "--baseline-mode",
            "fast-lookup",
            "--candidate-mode",
            "fast-insert",
            "--baseline-config",
            "baseline.toml",
            "--candidate-config",
            "candidate.toml",
            "--latency-sample-k",
            "64",
            "--latency-sample-every",
            "8",
            "--metrics-max-ticks",
            "100",
            "--out-dir",
            out_dir.as_posix(),
        ],
    )

    assert hooks.ab_args is not None
    kwargs = hooks.ab_args["kwargs"]
    assert kwargs["baseline_label"] == "baseline run"
    assert kwargs["candidate_label"] == "candidate run"
    assert kwargs["baseline_mode"] == "fast-lookup"
    assert kwargs["candidate_mode"] == "fast-insert"
    assert kwargs["baseline_config"] == "baseline.toml"
    assert kwargs["candidate_config"] == "candidate.toml"
    assert kwargs["latency_sample_k"] == 64
    assert kwargs["latency_sample_every"] == 8
    assert kwargs["metrics_max_ticks"] == 100
    assert kwargs["metrics_dir"].endswith("out/artifacts")
    assert kwargs["json_out"].endswith("baseline_run_vs_candidate_run.json")
    assert kwargs["markdown_out"].endswith("baseline_run_vs_candidate_run.md")

    assert hooks.emitted == {"data": {"status": "ok", "kwargs": kwargs}}
    assert (out_dir / "artifacts").is_dir()


def test_configure_ab_compare_respects_no_artifacts(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli ab-compare")
    handler_factory = commands._configure_ab_compare

    csv_path = tmp_path / "job.csv"
    csv_path.write_text("header\n", encoding="utf-8")

    json_out = tmp_path / "custom.json"
    md_out = tmp_path / "custom.md"

    hooks = _invoke(
        handler_factory,
        parser,
        [
            "--csv",
            csv_path.as_posix(),
            "--out-dir",
            (tmp_path / "out").as_posix(),
            "--json-out",
            json_out.as_posix(),
            "--markdown-out",
            md_out.as_posix(),
            "--no-artifacts",
        ],
    )

    kwargs = hooks.ab_args["kwargs"]  # type: ignore[index]
    assert kwargs["metrics_dir"] is None
    assert kwargs["markdown_out"] == md_out.as_posix()
    assert kwargs["json_out"] == json_out.as_posix()


def test_configure_profile_requires_csv_argument() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli profile")
    handler_factory = commands._configure_profile
    guard = _SentinelGuard()
    ctx = _build_cli_context(
        guard,
        profile_csv=lambda path: "hybrid",
        emit_success=lambda *args, **kwargs: None,
    )
    handler_factory(parser, ctx)
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_configure_profile_invokes_context_and_then_command(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli profile")
    hooks = _BasicHooks()
    guard = _SentinelGuard()
    ctx = _build_cli_context(
        guard,
        profile_csv=hooks.profile_csv,
        invoke_main=hooks.invoke_main,
        emit_success=hooks.emit_success,
    )
    handler = commands._configure_profile(parser, ctx)
    csv_path = tmp_path / "workload.csv"
    csv_path.write_text("header", encoding="utf-8")
    result = handler(
        parser.parse_args(["--csv", csv_path.as_posix(), "--then", "run-csv", "--ops", "10"])
    )
    assert result == int(commands.Exit.OK)
    assert hooks.profile_args == [csv_path.as_posix()]
    assert hooks.emitted == {
        "command": "profile",
        "text": hooks.profile_return,
        "data": {"csv": csv_path.as_posix(), "recommended_mode": hooks.profile_return},
    }
    assert hooks.invoked == ["--mode", hooks.profile_return, "run-csv", "--ops", "10"]


def test_configure_profile_without_then_does_not_invoke_main(tmp_path: Path) -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli profile")
    hooks = _BasicHooks()
    guard = _SentinelGuard()
    ctx = _build_cli_context(
        guard,
        profile_csv=hooks.profile_csv,
        invoke_main=hooks.invoke_main,
        emit_success=hooks.emit_success,
    )
    handler = commands._configure_profile(parser, ctx)
    csv_path = tmp_path / "workload.csv"
    csv_path.write_text("header", encoding="utf-8")
    result = handler(parser.parse_args(["--csv", csv_path.as_posix()]))
    assert result == int(commands.Exit.OK)
    assert hooks.profile_args == [csv_path.as_posix()]
    assert hooks.invoked is None


def test_configure_put_runs_operation_and_emits_success() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli put")
    parser.add_argument("--mode", default="hybrid")
    hooks = _BasicHooks(next_output="ok")
    ctx = _build_cli_context(
        _SentinelGuard(),
        build_map=hooks.build_map,
        run_op=hooks.run_op,
        emit_success=hooks.emit_success,
    )

    handler = commands._configure_put(parser, ctx)
    result = handler(parser.parse_args(["--mode", "hybrid", "foo", "bar"]))

    assert result == int(commands.Exit.OK)
    assert hooks.build_modes == ["hybrid"]
    assert hooks.run_calls == [({"mode": "hybrid"}, "put", "foo", "bar")]
    assert hooks.emitted == {
        "command": "put",
        "text": "ok",
        "data": {"mode": "hybrid", "key": "foo", "value": "bar", "result": "ok"},
    }


def test_configure_get_emits_found_value() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli get")
    parser.add_argument("--mode", default="hybrid")
    hooks = _BasicHooks(next_output="value42")
    ctx = _build_cli_context(
        _SentinelGuard(),
        build_map=hooks.build_map,
        run_op=hooks.run_op,
        emit_success=hooks.emit_success,
    )

    handler = commands._configure_get(parser, ctx)
    result = handler(parser.parse_args(["--mode", "hybrid", "foo"]))

    assert result == int(commands.Exit.OK)
    assert hooks.run_calls == [({"mode": "hybrid"}, "get", "foo", None)]
    assert hooks.emitted == {
        "command": "get",
        "text": "value42",
        "data": {"mode": "hybrid", "key": "foo", "found": True, "value": "value42"},
    }


def test_configure_del_marks_deleted_items() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli del")
    parser.add_argument("--mode", default="hybrid")
    hooks = _BasicHooks(next_output="1")
    ctx = _build_cli_context(
        _SentinelGuard(),
        build_map=hooks.build_map,
        run_op=hooks.run_op,
        emit_success=hooks.emit_success,
    )

    handler = commands._configure_del(parser, ctx)
    result = handler(parser.parse_args(["--mode", "hybrid", "foo"]))

    assert result == int(commands.Exit.OK)
    assert hooks.run_calls == [({"mode": "hybrid"}, "del", "foo", None)]
    assert hooks.emitted == {
        "command": "del",
        "text": "1",
        "data": {"mode": "hybrid", "key": "foo", "deleted": True},
    }


def test_configure_items_parses_output_into_items() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli items")
    parser.add_argument("--mode", default="hybrid")
    hooks = _BasicHooks(next_output="foo,bar\nbaz,")
    ctx = _build_cli_context(
        _SentinelGuard(),
        build_map=hooks.build_map,
        run_op=hooks.run_op,
        emit_success=hooks.emit_success,
    )

    handler = commands._configure_items(parser, ctx)
    result = handler(parser.parse_args(["--mode", "hybrid"]))

    assert result == int(commands.Exit.OK)
    assert hooks.run_calls == [({"mode": "hybrid"}, "items", None, None)]
    assert hooks.emitted == {
        "command": "items",
        "text": "foo,bar\nbaz,",
        "data": {
            "mode": "hybrid",
            "count": 2,
            "items": [{"key": "foo", "value": "bar"}, {"key": "baz", "value": ""}],
        },
    }
