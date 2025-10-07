import io
import pickle

import pytest

from adhash.io import safe_pickle


class _ForbiddenObject:
    pass


def test_safe_pickle_dump_and_load_roundtrip():
    payload = {"alpha": [1, 2, 3], "beta": ("x", "y")}
    buffer = io.BytesIO()
    safe_pickle.dump(payload, buffer)
    buffer.seek(0)
    assert safe_pickle.load(buffer) == payload


def test_safe_pickle_dumps_and_loads_rejects_disallowed_globals():
    data = pickle.dumps(_ForbiddenObject())
    with pytest.raises(pickle.UnpicklingError):
        safe_pickle.loads(data)


def test_restricted_unpickler_allows_known_types():
    unpickler = safe_pickle._RestrictedUnpickler(io.BytesIO())
    assert unpickler.find_class("builtins", "dict") is dict
    assert unpickler.find_class("collections", "defaultdict")
    with pytest.raises(pickle.UnpicklingError):
        unpickler.find_class("collections", "Counter")
