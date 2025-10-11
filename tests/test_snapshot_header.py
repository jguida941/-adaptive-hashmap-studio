import struct
from pathlib import Path

import pytest

import adhash.io.snapshot_header as sh
from adhash.io.snapshot_header import (
    FLAG_GZIP,
    MAGIC,
    describe_snapshot,
    dumps_snapshot,
    loads_snapshot,
    read_snapshot,
    write_snapshot,
)


def test_snapshot_roundtrip(tmp_path: Path) -> None:
    payload = {"answer": 42, "items": [1, 2, 3]}
    path = tmp_path / "snap.bin"
    write_snapshot(path, payload, compress=True)
    assert read_snapshot(path) == payload


def test_snapshot_checksum_detects_tamper() -> None:
    payload = ["a", "b", "c"]
    blob = bytearray(dumps_snapshot(payload, compress=False))
    blob[-1] ^= 0xFF
    with pytest.raises(ValueError, match="Checksum mismatch"):
        loads_snapshot(bytes(blob))


def test_snapshot_rejects_bad_magic() -> None:
    blob = bytearray(dumps_snapshot({"x": 1}, compress=False))
    blob[0] ^= 0xFF
    with pytest.raises(ValueError, match="Bad magic"):
        loads_snapshot(bytes(blob))


def test_snapshot_rejects_unknown_version() -> None:
    blob = bytearray(dumps_snapshot({"x": 1}, compress=False))
    struct.pack_into(">H", blob, len(MAGIC), 2)
    with pytest.raises(ValueError, match="Unsupported snapshot version"):
        loads_snapshot(bytes(blob))


def test_snapshot_rejects_unknown_flags() -> None:
    blob = bytearray(dumps_snapshot({"x": 1}, compress=False))
    struct.pack_into(">B", blob, len(MAGIC) + 2, 0b10)
    with pytest.raises(ValueError, match="Unsupported snapshot flags"):
        loads_snapshot(bytes(blob))


def test_snapshot_rejects_oversized_payload() -> None:
    oversized_header = struct.pack(
        sh.HEADER_FMT,
        MAGIC,
        1,
        0,
        0,
        32,
        sh._MAX_PAYLOAD_BYTES + 1,
    )
    blob = oversized_header + b"0" * 32
    with pytest.raises(ValueError, match="payload exceeds"):
        loads_snapshot(blob)


def test_snapshot_gzip_flag_requires_valid_payload() -> None:
    blob = bytearray(dumps_snapshot({"x": 1}, compress=False))
    struct.pack_into(">B", blob, len(MAGIC) + 2, FLAG_GZIP)
    with pytest.raises(ValueError, match="Corrupt gzip payload"):
        loads_snapshot(bytes(blob))


def test_describe_snapshot_reads_header(tmp_path: Path) -> None:
    payload = {"value": 42}
    path = tmp_path / "desc.snap"
    write_snapshot(path, payload, compress=False)
    descriptor = describe_snapshot(path)
    assert descriptor.header.payload_len > 0
    assert len(descriptor.checksum_hex) == descriptor.header.checksum_len * 2
