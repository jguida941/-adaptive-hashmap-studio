import gzip
from pathlib import Path
from unittest import mock

import pytest

from adhash.io import safe_pickle, snapshot


def test_open_snapshot_for_read_handles_gzip(tmp_path: Path):
    target = tmp_path / "sample.snapshot.gz"
    with gzip.open(target, "wb") as fh:
        fh.write(b"payload")

    with snapshot.open_snapshot_for_read(str(target)) as fh:
        assert fh.read() == b"payload"


def test_open_snapshot_for_write_respects_compress_flag(tmp_path: Path):
    target = tmp_path / "sample.snapshot"
    with snapshot.open_snapshot_for_write(str(target), compress=True) as fh:
        fh.write(b"payload")

    with gzip.open(target, "rb") as fh:
        assert fh.read() == b"payload"


def test_load_snapshot_any_falls_back_to_legacy_pickle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    legacy_file = tmp_path / "legacy.snapshot"
    with snapshot.open_snapshot_for_write(str(legacy_file), compress=False) as fh:
        safe_pickle.dump({"sentinel": 1}, fh)

    monkeypatch.setattr(snapshot, "read_versioned_snapshot", mock.Mock(side_effect=ValueError("bad header")))

    loaded = snapshot.load_snapshot_any(str(legacy_file))
    assert loaded == {"sentinel": 1}


def test_save_snapshot_any_falls_back_to_legacy_pickle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "legacy.snapshot"
    monkeypatch.setattr(snapshot, "write_versioned_snapshot", mock.Mock(side_effect=RuntimeError("boom")))

    snapshot.save_snapshot_any({"sentinel": 2}, str(target), compress=False)

    with snapshot.open_snapshot_for_read(str(target)) as fh:
        assert safe_pickle.load(fh) == {"sentinel": 2}
