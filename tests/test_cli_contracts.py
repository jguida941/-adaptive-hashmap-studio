import json
import shlex
import subprocess
import sys
from pathlib import Path

CLI = [sys.executable, "hashmap_cli.py"]


def run_cli(cmd: str, cwd: Path | None = None):
    proc = subprocess.run(CLI + shlex.split(cmd), capture_output=True, text=True, cwd=cwd)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


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
