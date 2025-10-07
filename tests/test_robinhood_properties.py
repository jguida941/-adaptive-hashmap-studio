from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from hypothesis import given, settings, strategies as st

from adhash.core.maps import RobinHoodMap


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


def _operation_strategy() -> st.SearchStrategy[Tuple[str, Any | None, int | None]]:
    key = _key_strategy()
    value = _value_strategy()
    put_op = st.tuples(st.just("put"), key, value)
    get_op = st.tuples(st.just("get"), key, st.none())
    delete_op = st.tuples(st.just("delete"), key, st.none())
    compact_op = st.tuples(st.just("compact"), st.none(), st.none())
    return st.one_of(put_op, get_op, delete_op, compact_op)


def _items_to_dict(items: Iterable[Tuple[Any, Any]]) -> Dict[Any, Any]:
    return dict(items)


@settings(max_examples=150, deadline=None)
@given(st.lists(_operation_strategy(), min_size=1, max_size=120))
def test_robinhood_map_behaves_like_dict(operations: list[Tuple[str, Any | None, int | None]]) -> None:
    map_impl = RobinHoodMap(initial_capacity=8)
    model: Dict[Any, int] = {}
    seen_keys: set[Any] = set()

    for op, key, maybe_value in operations:
        if op == "compact":
            map_impl.compact()
            assert _items_to_dict(map_impl.items()) == model
            assert len(map_impl) == len(model)
            continue

        assert key is not None
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

    # Compacting at the end should not change observable state.
    map_impl.compact()
    assert _items_to_dict(map_impl.items()) == model
    assert len(map_impl) == len(model)


def test_robinhood_put_reuses_tombstone_without_duplicates() -> None:
    map_impl = RobinHoodMap(initial_capacity=8)
    map_impl.put("a", 1)
    map_impl.put("b", 2)
    assert len(map_impl) == 2
    assert map_impl.delete("a") is True
    map_impl.put("b", 3)
    items = list(map_impl.items())
    assert items.count(("b", 3)) == 1
    assert all(key != "a" for key, _ in items)
    assert len(map_impl) == 1
