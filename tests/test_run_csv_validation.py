from __future__ import annotations

from pathlib import Path

import pytest

from adhash.contracts.error import BadInputError
from adhash.hashmap_cli import run_csv


def _write_csv(path: Path, rows: str) -> None:
    path.write_text("op,key,value\n" + rows, encoding="utf-8")


def test_run_csv_dry_run_reports_size(tmp_path: Path) -> None:
    csv_path = tmp_path / "work.csv"
    _write_csv(csv_path, "put,K1,1\nget,K1,\n")

    result = run_csv(str(csv_path), "adaptive", dry_run=True)

    assert result["status"] == "validated"
    assert result["rows"] == 2
    assert result["size_bytes"] == csv_path.stat().st_size
    assert pytest.approx(result["size_mib"], rel=1e-6) == result["size_bytes"] / (1024 * 1024)


def test_run_csv_dry_run_missing_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_header.csv"
    csv_path.write_text("op,key\nput,K1\n", encoding="utf-8")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive", dry_run=True)


def test_run_csv_dry_run_unknown_operation(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_op.csv"
    _write_csv(csv_path, "noop,K1,\n")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive", dry_run=True)


def test_run_csv_dry_run_missing_key(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing_key.csv"
    _write_csv(csv_path, "put, ,1\n")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive", dry_run=True)


def test_run_csv_dry_run_put_missing_value(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing_value.csv"
    _write_csv(csv_path, "put,K1, \n")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive", dry_run=True)


def test_run_csv_enforces_row_limit(tmp_path: Path) -> None:
    csv_path = tmp_path / "row_limit.csv"
    _write_csv(csv_path, "put,K1,1\nput,K2,2\n")

    with pytest.raises(BadInputError):
        run_csv(str(csv_path), "adaptive", dry_run=True, csv_max_rows=1)


def test_run_csv_latency_preset_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "preset.csv"
    _write_csv(csv_path, "put,K1,1\n")

    monkeypatch.setenv("ADHASH_LATENCY_BUCKETS", "unknownPreset")

    result = run_csv(str(csv_path), "adaptive", dry_run=True)

    assert result["status"] == "validated"

    monkeypatch.delenv("ADHASH_LATENCY_BUCKETS", raising=False)
