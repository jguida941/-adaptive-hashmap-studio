from __future__ import annotations

from pathlib import Path

import pytest

from adhash.cli import app
from adhash.core.maps import RobinHoodMap
from adhash.io.snapshot import save_snapshot_any


def test_verify_snapshot_robinhood(tmp_path: Path) -> None:
    snap_path = tmp_path / "rh.snapshot"
    m = RobinHoodMap(initial_capacity=8)
    m.put("key", "value")
    save_snapshot_any(m, str(snap_path), compress=False)
    rc = app.verify_snapshot(str(snap_path), verbose=True)
    assert rc == 0


def test_verify_snapshot_repair(tmp_path: Path) -> None:
    snap_path = tmp_path / "rh.snapshot"
    out_path = tmp_path / "repaired.snapshot"
    m = RobinHoodMap(initial_capacity=8)
    for idx in range(4):
        m.put(f"k{idx}", f"v{idx}")
    save_snapshot_any(m, str(snap_path), compress=False)
    rc = app.verify_snapshot(str(snap_path), verbose=False, repair=True, repair_out=str(out_path))
    assert rc == 0
    assert out_path.exists()


def test_verify_snapshot_unsupported_object(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snap_path = tmp_path / "dict.snapshot"
    save_snapshot_any({"foo": "bar"}, str(snap_path), compress=False)
    rc = app.verify_snapshot(str(snap_path))
    assert rc == 1
    assert "ERROR" in capsys.readouterr().out
