from __future__ import annotations

from adhash.metrics.core import Metrics


def test_update_rates_preserves_zero_throughput() -> None:
    metrics = Metrics()
    tick = {
        "ops": 10,
        "t": 1.0,
        "ops_per_second": 0,
    }
    metrics.update_rates(tick)
    assert tick["ops_per_second_instant"] == 0
    assert tick["ops_per_second_ema"] == 0
    assert metrics._last_instant == 0
