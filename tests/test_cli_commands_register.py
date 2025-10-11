from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any

from adhash.cli.commands import CLIContext, register_subcommands


class _SentinelGuard:
    def __init__(self) -> None:
        self.seen: list[Any] = []

    def __call__(self, fn: Any) -> Any:
        self.seen.append(fn)

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper.__wrapped_fn__ = fn  # type: ignore[attr-defined]
        wrapper.__guard_wrapped__ = True  # type: ignore[attr-defined]
        return wrapper


def _build_cli_context(guard: _SentinelGuard, **overrides: Any) -> CLIContext:
    """Return a CLIContext populated with simple stubs (overridable for specific tests)."""

    def emit_success(*_args: Any, **_kwargs: Any) -> None:
        return None

    def build_map(_mode: str) -> object:
        return object()

    def run_op(_map_obj: object, op: str, _key: str | None, _value: str | None) -> str | None:
        return "1" if op == "del" else ""

    def profile_csv(_path: str) -> str:
        return "hybrid"

    def run_csv(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "ok"}

    def generate_csv(*_args: Any, **_kwargs: Any) -> None:
        return None

    def run_config_wizard(path: str) -> Path:
        return Path(path)

    def run_config_editor(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    def run_ab_compare(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"delta": 0}

    def verify_snapshot(*_args: Any, **_kwargs: Any) -> int:
        return 0

    def analyze_workload(*_args: Any, **_kwargs: Any) -> object:
        return object()

    def invoke_main(_argv: list[str]) -> int:
        return 0

    def json_enabled() -> bool:
        return False

    return CLIContext(
        emit_success=overrides.get("emit_success", emit_success),
        build_map=overrides.get("build_map", build_map),
        run_op=overrides.get("run_op", run_op),
        profile_csv=overrides.get("profile_csv", profile_csv),
        run_csv=overrides.get("run_csv", run_csv),
        generate_csv=overrides.get("generate_csv", generate_csv),
        run_config_wizard=overrides.get("run_config_wizard", run_config_wizard),
        run_config_editor=overrides.get("run_config_editor", run_config_editor),
        run_ab_compare=overrides.get("run_ab_compare", run_ab_compare),
        verify_snapshot=overrides.get("verify_snapshot", verify_snapshot),
        analyze_workload=overrides.get("analyze_workload", analyze_workload),
        invoke_main=overrides.get("invoke_main", invoke_main),
        logger=logging.getLogger("adhash.cli.commands.test"),
        json_enabled=json_enabled,
        robinhood_cls=overrides.get("robinhood_cls", object),
        guard=guard,
        latency_bucket_choices=["p50"],
    )


def test_register_subcommands_registers_every_handler_with_guard() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli")
    subparsers = parser.add_subparsers(dest="command")

    sentinel_guard = _SentinelGuard()
    ctx = _build_cli_context(sentinel_guard)

    handlers = register_subcommands(subparsers, ctx)

    expected_commands = {
        "put",
        "get",
        "del",
        "items",
        "profile",
        "generate-csv",
        "run-csv",
        "workload-dna",
        "inspect-snapshot",
        "config-wizard",
        "config-edit",
        "ab-compare",
        "mission-control",
        "serve",
        "compact-snapshot",
        "verify-snapshot",
        "probe-visualize",
    }

    assert set(handlers.keys()) == expected_commands
    assert set(subparsers.choices.keys()) == expected_commands
    assert len(sentinel_guard.seen) == len(expected_commands)

    for name, handler in handlers.items():
        assert getattr(handler, "__guard_wrapped__", False), f"{name} not wrapped by guard"
        assert handler.__wrapped_fn__ in sentinel_guard.seen  # type: ignore[attr-defined]

    put_parser = subparsers.choices["put"]
    put_dests = {action.dest for action in put_parser._actions if getattr(action, "dest", None)}
    assert {"key", "value"} <= put_dests

    get_parser = subparsers.choices["get"]
    get_dests = {action.dest for action in get_parser._actions if getattr(action, "dest", None)}
    assert "key" in get_dests

    del_parser = subparsers.choices["del"]
    del_dests = {action.dest for action in del_parser._actions if getattr(action, "dest", None)}
    assert "key" in del_dests
    for original in sentinel_guard.seen:
        assert callable(original), "register_subcommands should register callable handlers"


def test_register_subcommands_populates_help_text() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli")
    subparsers = parser.add_subparsers(dest="command")

    sentinel_guard = _SentinelGuard()
    ctx = _build_cli_context(sentinel_guard)

    register_subcommands(subparsers, ctx)

    help_by_command = {action.dest: action.help for action in subparsers._choices_actions}

    assert help_by_command["put"] is None
    assert help_by_command["get"] is None
    assert help_by_command["del"] is None
    assert help_by_command["items"] is None
    assert help_by_command["profile"] == "Profile a CSV workload and print recommended backend."
    assert help_by_command["generate-csv"] == "Generate a synthetic workload CSV."
    assert (
        help_by_command["run-csv"]
        == "Replay a CSV workload (metrics, snapshots, compaction, JSON summary)."
    )
    assert (
        help_by_command["workload-dna"]
        == "Analyze a CSV workload for ratios, skew, and collision risk."
    )
    assert (
        help_by_command["inspect-snapshot"]
        == "Inspect snapshot metadata and optionally search for keys."
    )
    assert help_by_command["config-wizard"] == "Interactively generate a TOML config file."
    assert (
        help_by_command["config-edit"]
        == "Edit a config file with preset support using the wizard schema."
    )
    assert (
        help_by_command["ab-compare"]
        == "Run paired run-csv jobs and compute throughput/latency deltas."
    )
    assert help_by_command["mission-control"] == "Launch the Mission Control desktop UI (PyQt6)."
    assert help_by_command["serve"] == "Serve the dashboard/metrics API without running a workload."
    assert help_by_command["compact-snapshot"] == "Compact a RobinHoodMap snapshot offline."
    assert (
        help_by_command["verify-snapshot"]
        == "Verify invariants of a snapshot; optional safe repair (RobinHoodMap)."
    )
    assert (
        help_by_command["probe-visualize"]
        == "Trace probe paths for GET/PUT operations (text/JSON)."
    )


def test_register_subcommands_handlers_capture_cli_context() -> None:
    parser = argparse.ArgumentParser(prog="adhash-cli")
    subparsers = parser.add_subparsers(dest="command")

    sentinel_guard = _SentinelGuard()
    ctx = _build_cli_context(sentinel_guard)

    handlers = register_subcommands(subparsers, ctx)

    commands_requiring_ctx = {
        "put",
        "get",
        "del",
        "items",
        "profile",
        "generate-csv",
        "run-csv",
        "workload-dna",
        "inspect-snapshot",
        "config-wizard",
        "config-edit",
        "ab-compare",
        "serve",
        "compact-snapshot",
        "verify-snapshot",
        "probe-visualize",
    }

    for name in commands_requiring_ctx:
        handler = handlers[name]
        original = handler.__wrapped_fn__  # type: ignore[attr-defined]
        closure = original.__closure__
        assert closure, f"{name} handler should close over CLIContext"
        assert any(cell.cell_contents is ctx for cell in closure), (
            f"{name} handler missing ctx closure"
        )
