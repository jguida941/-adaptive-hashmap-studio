from pathlib import Path

import pytest

from adhash.io.snapshot_header import dumps_snapshot, loads_snapshot, read_snapshot, write_snapshot


def test_snapshot_roundtrip(tmp_path: Path) -> None:
    payload = {"answer": 42, "items": [1, 2, 3]}
    path = tmp_path / "snap.bin"
    write_snapshot(path, payload, compress=True)
    assert read_snapshot(path) == payload


def test_snapshot_checksum_detects_tamper(tmp_path: Path) -> None:
    payload = ["a", "b", "c"]
    blob = bytearray(dumps_snapshot(payload, compress=False))
    blob[-1] ^= 0xFF
    with pytest.raises(ValueError, match="Checksum mismatch"):
        loads_snapshot(bytes(blob))
