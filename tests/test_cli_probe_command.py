from __future__ import annotations

import contextlib
import io
import json
import os
import types
from pathlib import Path

import hashmap_cli
from adhash.core.maps import RobinHoodMap
from adhash.io.snapshot import save_snapshot_any


def run_cli(args: list[str], cwd: Path | None = None) -> types.SimpleNamespace:
    stdout = io.StringIO()
    stderr = io.StringIO()
    prev_dir = Path.cwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = hashmap_cli.main(args)
            except SystemExit as exc:
                if isinstance(exc.code, int):
                    code = exc.code
                elif exc.code is None:
                    code = 0
                else:
                    code = 1
    finally:
        hashmap_cli.OUTPUT_JSON = False
        if cwd is not None:
            os.chdir(prev_dir)
    return types.SimpleNamespace(
        returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue()
    )


def test_probe_visualize_text() -> None:
    result = run_cli(
        [
            "--mode",
            "fast-lookup",
            "probe-visualize",
            "--operation",
            "put",
            "--key",
            "K1",
            "--value",
            "V1",
            "--seed",
            "A=1",
            "--seed",
            "B=2",
        ]
    )
    assert result.returncode == 0
    assert "Probe visualization" in result.stdout
    assert "Steps:" in result.stdout


def test_probe_visualize_json_output() -> None:
    result = run_cli(
        [
            "--mode",
            "fast-lookup",
            "--json",
            "probe-visualize",
            "--operation",
            "get",
            "--key",
            "missing",
        ]
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    trace = payload["trace"]
    assert trace["backend"] == "robinhood"
    assert trace["operation"] == "get"


def test_probe_visualize_requires_value_for_put() -> None:
    result = run_cli(
        [
            "probe-visualize",
            "--operation",
            "put",
            "--key",
            "K1",
        ]
    )
    assert result.returncode == 2
    assert "requires --value" in result.stderr


def test_probe_visualize_snapshot(tmp_path: Path) -> None:
    snap_path = tmp_path / "map.pkl"
    m = RobinHoodMap(initial_capacity=8)
    m.put("foo", "bar")
    save_snapshot_any(m, str(snap_path), False)

    result = run_cli(
        [
            "probe-visualize",
            "--operation",
            "get",
            "--key",
            "foo",
            "--snapshot",
            str(snap_path),
        ]
    )
    assert result.returncode == 0
    assert "Snapshot:" in result.stdout
    assert "foo" in result.stdout


def test_probe_visualize_invalid_seed_format() -> None:
    result = run_cli(
        [
            "probe-visualize",
            "--operation",
            "get",
            "--key",
            "K1",
            "--seed",
            "not-key-value",
        ]
    )
    assert result.returncode == 2
    assert "KEY=VALUE" in result.stderr


def test_probe_visualize_missing_snapshot_file(tmp_path: Path) -> None:
    missing = tmp_path / "absent.pkl"
    result = run_cli(
        [
            "probe-visualize",
            "--operation",
            "get",
            "--key",
            "foo",
            "--snapshot",
            str(missing),
        ]
    )
    assert result.returncode == 5
    assert str(missing) in result.stderr


def test_probe_visualize_export_json(tmp_path: Path) -> None:
    target = tmp_path / "trace.json"
    result = run_cli(
        [
            "probe-visualize",
            "--operation",
            "get",
            "--key",
            "foo",
            "--export-json",
            str(target),
        ]
    )
    assert result.returncode == 0
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["operation"] == "get"
