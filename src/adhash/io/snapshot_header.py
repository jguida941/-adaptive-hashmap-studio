"""Versioned snapshot format with checksum protection."""

from __future__ import annotations

import gzip
import hashlib
import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Tuple

from .safe_pickle import dumps as safe_dumps, loads as safe_loads

MAGIC = b"ADHSNAP1"
HEADER_FMT = ">8s H B B H Q"  # magic, version, flags, reserved, checksum length, payload length
HEADER_SIZE = struct.calcsize(HEADER_FMT)
FLAG_GZIP = 0b00000001
_MAX_PAYLOAD_BYTES = 256 * 1024 * 1024  # 256 MiB default safety cap


@dataclass(slots=True, frozen=True)
class SnapshotHeader:
    """Header describing the on-disk snapshot payload."""

    version: int = 1
    flags: int = 0
    checksum_len: int = 32
    payload_len: int = 0


def _blake2b(data: bytes, digest_size: int = 32) -> bytes:
    h = hashlib.blake2b(digest_size=digest_size)
    h.update(data)
    return h.digest()


def _pack_header(header: SnapshotHeader) -> bytes:
    return struct.pack(
        HEADER_FMT,
        MAGIC,
        header.version,
        header.flags,
        0,
        header.checksum_len,
        header.payload_len,
    )


def _unpack_header(data: bytes) -> Tuple[SnapshotHeader, int]:
    if len(data) < HEADER_SIZE:
        raise ValueError("Header too short")
    magic, version, flags, _reserved, checksum_len, payload_len = struct.unpack(
        HEADER_FMT, data[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ValueError("Bad magic")
    if version != 1:
        raise ValueError(f"Unsupported snapshot version {version}")
    if flags & ~FLAG_GZIP:
        raise ValueError(f"Unsupported snapshot flags: {flags:#04x}")
    if payload_len > _MAX_PAYLOAD_BYTES:
        raise ValueError("Snapshot payload exceeds maximum allowed size")
    return (
        SnapshotHeader(
            version=version, flags=flags, checksum_len=checksum_len, payload_len=payload_len
        ),
        HEADER_SIZE,
    )


def dumps_snapshot(obj: Any, *, compress: bool = True) -> bytes:
    """Serialize an object to `[header][checksum][payload]` bytes."""

    payload = safe_dumps(obj)
    flags = 0
    if compress:
        with io.BytesIO() as buffer:
            with gzip.GzipFile(fileobj=buffer, mode="wb") as gz:
                gz.write(payload)
            payload = buffer.getvalue()
        flags |= FLAG_GZIP
    checksum = _blake2b(payload, digest_size=32)
    header = SnapshotHeader(
        version=1, flags=flags, checksum_len=len(checksum), payload_len=len(payload)
    )
    return _pack_header(header) + checksum + payload


def loads_snapshot(blob: bytes) -> Any:
    """Deserialize bytes produced by :func:`dumps_snapshot`."""

    header, offset = _unpack_header(blob)
    checksum_end = offset + header.checksum_len
    if len(blob) < checksum_end + header.payload_len:
        raise ValueError("Truncated snapshot")
    checksum = blob[offset:checksum_end]
    payload = blob[checksum_end : checksum_end + header.payload_len]
    expected = _blake2b(payload, digest_size=header.checksum_len)
    if checksum != expected:
        raise ValueError("Checksum mismatch")
    if header.flags & FLAG_GZIP:
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as gz:
                payload = gz.read()
        except OSError as exc:
            raise ValueError(f"Corrupt gzip payload: {exc}") from exc
    return safe_loads(payload)


def write_snapshot(path: Path, obj: Any, *, compress: bool = True) -> None:
    """Write a snapshot to disk, creating parent directories as needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dumps_snapshot(obj, compress=compress))


def read_snapshot(path: Path) -> Any:
    """Read a snapshot from disk."""

    return loads_snapshot(path.read_bytes())


@dataclass(slots=True, frozen=True)
class SnapshotDescriptor:
    """Lightweight metadata view of a snapshot file."""

    header: SnapshotHeader
    checksum_hex: str

    @property
    def compressed(self) -> bool:
        return bool(self.header.flags & FLAG_GZIP)


def describe_snapshot(path: Path) -> SnapshotDescriptor:
    """Return header/checksum metadata without deserialising the payload."""

    blob = path.read_bytes()
    header, offset = _unpack_header(blob)
    checksum_end = offset + header.checksum_len
    if len(blob) < checksum_end:
        raise ValueError("Snapshot file truncated before checksum")
    checksum = blob[offset:checksum_end]
    return SnapshotDescriptor(header=header, checksum_hex=checksum.hex())


__all__ = [
    "SnapshotHeader",
    "SnapshotDescriptor",
    "describe_snapshot",
    "write_snapshot",
    "read_snapshot",
    "dumps_snapshot",
    "loads_snapshot",
]
