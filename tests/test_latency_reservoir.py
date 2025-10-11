from __future__ import annotations

import pytest

from adhash.core.latency import (
    LATENCY_BUCKET_PRESETS_MS,
    Reservoir,
    _ReservoirRNG,
    resolve_latency_bucket_bounds,
)


def test_resolve_latency_bucket_bounds_handles_presets() -> None:
    key, bounds = resolve_latency_bucket_bounds(" micro ")
    assert key == "micro"
    assert bounds is LATENCY_BUCKET_PRESETS_MS["micro"]
    with pytest.raises(ValueError):
        resolve_latency_bucket_bounds("unknown")


def test_reservoir_rng_is_deterministic() -> None:
    rng_a = _ReservoirRNG(seed=1234)
    rng_b = _ReservoirRNG(seed=1234)
    sequence_a = [rng_a.randrange(17) for _ in range(5)]
    sequence_b = [rng_b.randrange(17) for _ in range(5)]
    assert sequence_a == sequence_b
    with pytest.raises(ValueError):
        rng_a.randrange(0)


def test_reservoir_offer_and_percentiles_are_stable() -> None:
    reservoir = Reservoir(k=3, seed=0xC0FFEE)
    for value in [0.1, 1.0, 2.0, 3.0, 4.0]:
        reservoir.offer(value)

    assert len(reservoir.buf) == 3
    assert reservoir.n == 5
    assert sorted(reservoir.buf) == [1.0, 2.0, 4.0]

    percentiles = reservoir.percentiles([0.5, 0.9])
    assert set(percentiles) == {"p50", "p90"}
    assert all(isinstance(v, float) for v in percentiles.values())

    empty = Reservoir(k=1, seed=42)
    assert empty.percentiles([0.5]) == {"p50": 0.0}


def test_reservoir_rng_system_random(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    class DummyRandom:
        def getrandbits(self, bits: int) -> int:
            calls.append(bits)
            return 1

    monkeypatch.setattr("adhash.core.latency.secrets.SystemRandom", lambda: DummyRandom())
    rng = _ReservoirRNG(seed=None)
    assert rng.randrange(5) == 1
    assert calls == [3]
    with pytest.raises(RuntimeError):
        rng._deterministic_bits(8)


def test_reservoir_rng_deterministic_bits_handles_partial_bytes() -> None:
    rng = _ReservoirRNG(seed=7)
    # bits=5 exercises branch that stitches together partial bytes
    value = rng._deterministic_bits(5)
    assert 0 <= value < (1 << 5)
    # bits=8 follows the straight-bytes path
    value_full = rng._deterministic_bits(8)
    assert 0 <= value_full < (1 << 8)
