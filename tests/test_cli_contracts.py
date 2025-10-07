import contextlib
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import hashmap_cli

CLI = [sys.executable, "-m", "hashmap_cli"]


def run_cli(cmd: str, cwd: Path | None = None):
    argv = shlex.split(cmd)
    stdout = io.StringIO()
    stderr = io.StringIO()
    prev_dir = Path.cwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = hashmap_cli.main(argv)
            except SystemExit as exc:  # CLI may call sys.exit
                code = exc.code if isinstance(exc.code, int) else 1
    finally:
        hashmap_cli.OUTPUT_JSON = False
        if cwd is not None:
            os.chdir(prev_dir)
    return code, stdout.getvalue().strip(), stderr.getvalue().strip()


def parse_error(stderr: str) -> dict:
    if not stderr.strip():
        return {}
    return json.loads(stderr.splitlines()[-1])


def test_run_csv_missing_file_returns_io(tmp_path: Path) -> None:
    code, _, err = run_cli("run-csv --csv missing.csv")
    env = parse_error(err)
    assert code == 5
    assert env.get("error") in {"IO", "FileNotFound"}


def test_run_csv_bad_header_returns_badinput(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("nope,missing\n", encoding="utf-8")
    code, _, err = run_cli(f"run-csv --csv {bad}")
    env = parse_error(err)
    assert code == 2
    assert env.get("error") in {"BadInput", "BadCSV"}
    assert "header" in env.get("detail", "").lower()


def test_run_csv_put_missing_value_reports_line(tmp_path: Path) -> None:
    bad = tmp_path / "bad_rows.csv"
    bad.write_text("op,key,value\nput,K1,\n", encoding="utf-8")
    code, _, err = run_cli(f"run-csv --csv {bad}")
    env = parse_error(err)
    assert code == 2
    assert env.get("error") == "BadInput"
    assert "missing value" in env.get("detail", "").lower()
    assert "line" in env.get("detail", "").lower()


def test_run_csv_row_limit(tmp_path: Path) -> None:
    limited = tmp_path / "limit.csv"
    limited.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")
    cmd = f"run-csv --csv {limited} --csv-max-rows 1"
    code, _, err = run_cli(cmd)
    env = parse_error(err)
    assert code == 2
    assert env.get("error") == "BadInput"
    assert "row limit" in env.get("detail", "").lower()


def test_run_csv_dry_run(tmp_path: Path) -> None:
    ok = tmp_path / "ok.csv"
    ok.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")
    code, out, err = run_cli(f"run-csv --csv {ok} --dry-run")
    assert code == 0
    assert "validation successful" in err.lower()


def test_put_json_output() -> None:
    code, out, err = run_cli("--json put K1 V1")
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "put"
    assert payload["key"] == "K1"
    assert payload["value"] == "V1"
    assert payload.get("result") == "OK"


def test_run_csv_dry_run_json(tmp_path: Path) -> None:
    ok = tmp_path / "ok.csv"
    ok.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")
    code, out, err = run_cli(f"--json run-csv --csv {ok} --dry-run")
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "run-csv"
    assert payload["status"] == "validated"
    assert payload["rows"] == 2
    assert payload["mode"] == "adaptive"


def test_run_csv_accepts_zero_metrics_port(tmp_path: Path) -> None:
    csv_path = tmp_path / "work.csv"
    csv_path.write_text("op,key,value\nput,K1,1\n", encoding="utf-8")
    code, out, err = run_cli(f"--json run-csv --csv {csv_path} --dry-run --metrics-port 0")
    assert code == 0
    payload = json.loads(out)
    assert payload["status"] == "validated"


def test_run_csv_json_with_snapshot(tmp_path: Path) -> None:
    csv_path = tmp_path / "work.csv"
    csv_path.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")
    snapshot_path = tmp_path / "snap.pkl"
    code, out, err = run_cli(f"--json run-csv --csv {csv_path} --snapshot-out {snapshot_path}")
    assert code == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["command"] == "run-csv"
    assert payload["status"] == "completed"
    assert payload["total_ops"] == 2
    assert payload["snapshot_written"] == str(snapshot_path)
    summary = payload["summary"]
    assert summary["total_ops"] == 2
    assert isinstance(summary["final_backend"], str)

    code, out, err = run_cli(f"--json verify-snapshot --in {snapshot_path}")
    assert code == 0
    verify_payload = json.loads(out)
    assert verify_payload["ok"] is True
    assert verify_payload["command"] == "verify-snapshot"
    assert verify_payload["repaired"] is False
    assert any("snapshot verified" in msg.lower() for msg in verify_payload.get("messages", []))


def test_inspect_snapshot_cli(tmp_path: Path) -> None:
    from adhash.core.maps import HybridAdaptiveHashMap
    from adhash.io.snapshot import save_snapshot_any

    snapshot_path = tmp_path / "inspector.pkl.gz"
    map_obj = HybridAdaptiveHashMap()
    map_obj.put("K1", "V1")
    map_obj.put("K2", "V2")
    save_snapshot_any(map_obj, str(snapshot_path), compress=True)

    code, out, err = run_cli(f"inspect-snapshot --in {snapshot_path} --limit 5")
    assert code == 0
    assert "Snapshot:" in out
    assert str(snapshot_path) in out

    code, out_json, err_json = run_cli(f"--json inspect-snapshot --in {snapshot_path} --key K1 --limit 3")
    assert code == 0
    payload = json.loads(out_json)
    assert payload["ok"] is True
    assert payload["command"] == "inspect-snapshot"
    key_section = payload.get("key")
    assert key_section is not None
    assert key_section["found"] is True
    assert key_section["value"]


@pytest.mark.parametrize("port_arg", ["auto", "0"])
def test_serve_auto_reports_bound_port(port_arg: str) -> None:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        CLI + ["serve", "--port", port_arg, "--host", "127.0.0.1"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    stdout = proc.stdout
    stderr = proc.stderr
    assert stdout is not None
    assert stderr is not None
    try:
        while True:
            line = stdout.readline()
            if not line:
                if proc.poll() is not None:
                    stderr_output = stderr.read()
                    if "Operation not permitted" in stderr_output:
                        pytest.skip("Socket binding not permitted in sandbox")
                    raise AssertionError(f"serve exited unexpectedly: {stderr_output}")
                continue
            line = line.strip()
            if line:
                break
        assert line.startswith("Dashboard:"), line
        match = re.search(r"http://localhost:(\d+)/", line)
        assert match is not None, line
        assert match.group(1) != "0", line
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
