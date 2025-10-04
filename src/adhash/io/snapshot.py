
"""Snapshot I/O helpers for Adaptive Hash Map."""

from __future__ import annotations

import gzip
import logging
import os
import pickle
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any, IO, cast

from .snapshot_header import read_snapshot as read_versioned_snapshot, write_snapshot as write_versioned_snapshot


logger = logging.getLogger("hashmap_cli")


def open_snapshot_for_read(path: str) -> IO[bytes]:
    """Open a snapshot path for binary reading (gzip-aware)."""

    if path.endswith(".gz"):
        return cast(IO[bytes], gzip.open(path, "rb"))
    return cast(IO[bytes], open(path, "rb"))


def open_snapshot_for_write(path: str, compress: bool) -> IO[bytes]:
    """Open a snapshot path for binary writing (gzip-aware)."""

    use_gz = compress or path.endswith(".gz")
    if use_gz:
        return cast(IO[bytes], gzip.open(path, "wb"))
    return cast(IO[bytes], open(path, "wb"))


def load_snapshot_any(path: str) -> Any:
    """Load a snapshot, falling back to legacy pickles on versioned failures."""

    target = Path(path)
    try:
        return read_versioned_snapshot(target)
    except Exception as exc:
        logger.debug("Falling back to legacy snapshot load for %s: %s", path, exc)
        with open_snapshot_for_read(str(target)) as fh:
            return pickle.load(fh)


def save_snapshot_any(obj: Any, path: str, compress: bool) -> None:
    """Persist an object via versioned header, falling back to legacy pickle."""

    target = Path(path)
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        try:
            write_versioned_snapshot(tmp_path, obj, compress=compress or path.endswith(".gz"))
        except Exception as exc:
            logger.debug("Falling back to legacy snapshot save for %s: %s", path, exc)
            with open_snapshot_for_write(str(tmp_path), compress or path.endswith(".gz")) as fh:
                pickle.dump(obj, fh)
        os.replace(tmp_path, target)
    except Exception:
        with suppress(FileNotFoundError):
            tmp_path.unlink()
        raise


def atomic_map_save(map_obj: Any, path: str | Path, *, compress: bool) -> None:
    """Save a map snapshot atomically by writing to a temp file first."""

    target = Path(path)
    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        map_obj.save(str(tmp_path), compress=compress)
        os.replace(tmp_path, target)
    except Exception:
        with suppress(FileNotFoundError):
            tmp_path.unlink()
        raise


__all__ = [
    "open_snapshot_for_read",
    "open_snapshot_for_write",
    "load_snapshot_any",
    "save_snapshot_any",
    "atomic_map_save",
]
