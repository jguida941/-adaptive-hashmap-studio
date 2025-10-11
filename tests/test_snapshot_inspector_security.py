from __future__ import annotations

import os
from pathlib import Path

import pytest

from adhash.mission_control.widgets import snapshot_inspector


def test_resolve_snapshot_path_enforces_trusted_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_root = tmp_path / "trusted"
    trusted_root.mkdir()
    trusted_file = trusted_root / "demo.pkl.gz"
    trusted_file.write_bytes(b"payload")

    monkeypatch.setenv("ADHASH_SNAPSHOT_TRUST_ROOTS", str(trusted_root))
    snapshot_inspector.reset_trusted_roots_cache()

    resolved = snapshot_inspector._resolve_snapshot_path(str(trusted_file))
    assert resolved == trusted_file.resolve()

    outside = tmp_path / "outside" / "demo.pkl.gz"
    outside.parent.mkdir()
    outside.write_bytes(b"payload")

    with pytest.raises(PermissionError):
        snapshot_inspector._resolve_snapshot_path(str(outside))


def test_resolve_snapshot_path_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted_root = tmp_path / "trusted"
    trusted_root.mkdir()
    monkeypatch.setenv("ADHASH_SNAPSHOT_TRUST_ROOTS", str(trusted_root))
    snapshot_inspector.reset_trusted_roots_cache()

    missing = trusted_root / "absent.pkl"
    with pytest.raises(FileNotFoundError):
        snapshot_inspector._resolve_snapshot_path(str(missing))


def test_invalid_trust_root_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    assert not missing_root.exists()
    valid_root = tmp_path / "valid"
    valid_root.mkdir()

    monkeypatch.setenv(
        "ADHASH_SNAPSHOT_TRUST_ROOTS",
        os.pathsep.join((str(missing_root), str(valid_root))),
    )
    snapshot_inspector.reset_trusted_roots_cache()

    with pytest.raises(RuntimeError):
        snapshot_inspector._trusted_snapshot_roots()


def test_resolve_snapshot_path_rejects_when_no_trusted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "demo.pkl.gz"
    target.write_bytes(b"payload")

    monkeypatch.setattr(snapshot_inspector, "_trusted_snapshot_roots", lambda: ())

    with pytest.raises(PermissionError):
        snapshot_inspector._resolve_snapshot_path(str(target))
