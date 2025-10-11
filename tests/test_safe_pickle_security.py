from __future__ import annotations

import datetime as _dt
import pickle  # noqa: S403

import pytest

from adhash.io import safe_pickle


def test_safe_pickle_allows_basic_collections() -> None:
    payload = {"a": [1, 2, 3], "b": ("x", 5)}
    data = pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL)
    restored = safe_pickle.loads(data)
    assert restored == payload


def test_safe_pickle_rejects_unlisted_globals() -> None:
    timestamp = _dt.datetime.now(tz=_dt.UTC)
    data = pickle.dumps(timestamp, protocol=pickle.HIGHEST_PROTOCOL)
    with pytest.raises(safe_pickle.UnpicklingError):
        safe_pickle.loads(data)
