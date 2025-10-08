from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from hypothesis import given, settings, strategies as st

from adhash.core.maps import TwoLevelChainingMap


@dataclass(frozen=True)
class CollidingKey:
    """Key whose hash intentionally collides with peers for stress testing."""

    value: int

    def __hash__(self) -> int:  # pragma: no cover - trivial wrapper
        return 0

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CK({self.value})"


def _key_strategy() -> st.SearchStrategy[Any]:
    small_ints = st.integers(-20, 20)
    colliding = st.builds(CollidingKey, st.integers(-10, 10))
    return st.one_of(small_ints, colliding)


def _value_strategy() -> st.SearchStrategy[int]:
    return st.integers(-1_000, 1_000)


def _operation_strategy() -> st.SearchStrategy[Tuple[str, Any, int | None]]:
    key = _key_strategy()
    value = _value_strategy()
    put_op = st.tuples(st.just("put"), key, value)
    get_op = st.tuples(st.just("get"), key, st.none())
    delete_op = st.tuples(st.just("delete"), key, st.none())
    return st.one_of(put_op, get_op, delete_op)


def _items_to_dict(items: Iterable[Tuple[Any, Any]]) -> Dict[Any, Any]:
    return dict(items)


@settings(max_examples=150, deadline=None)
@given(st.lists(_operation_strategy(), min_size=1, max_size=120))
def test_two_level_chaining_behaves_like_dict(
    operations: list[Tuple[str, Any, int | None]]
) -> None:
    map_impl = TwoLevelChainingMap(initial_buckets=4, groups_per_bucket=2)
    model: Dict[Any, int] = {}
    seen_keys: set[Any] = set()

    for op, key, maybe_value in operations:
        seen_keys.add(key)

        if op == "put":
            assert maybe_value is not None
            map_impl.put(key, maybe_value)
            model[key] = maybe_value
        elif op == "delete":
            expected_removed = key in model
            removed = map_impl.delete(key)
            assert removed is expected_removed
            model.pop(key, None)
        else:  # get
            expected = model.get(key)
            assert map_impl.get(key) == expected

        # Map length mirrors oracle.
        assert len(map_impl) == len(model)

        # Every seen key resolves identically.
        for candidate in seen_keys:
            assert map_impl.get(candidate) == model.get(candidate)

        # Items view matches oracle exactly.
        assert _items_to_dict(map_impl.items()) == model
