from __future__ import annotations

from adhash.core.maps import AdaptiveConfig, HybridAdaptiveHashMap, RobinHoodMap


def test_robinhood_migration_rounds_capacity() -> None:
    cfg = AdaptiveConfig(
        start_backend="chaining",
        initial_buckets=8,
        groups_per_bucket=8,
        initial_capacity_rh=8,
        incremental_batch=1024,
    )
    hmap = HybridAdaptiveHashMap(cfg)
    for i in range(6):  # ensure len backend not power of two
        hmap.put(f"k{i}", i)

    hmap._begin_migration("robinhood")
    target = hmap._migrate_target
    assert isinstance(target, RobinHoodMap)
    # len(self._backend) == 6 -> rounded to 8
    assert target._cap == 8
