from adhash.core.latency import (
    LATENCY_BUCKET_PRESETS_MS,
    resolve_latency_bucket_bounds,
)


def test_resolve_latency_bucket_bounds_micro() -> None:
    key, bounds = resolve_latency_bucket_bounds("micro")
    assert key == "micro"
    assert bounds[0] == 0.001
    assert bounds[-1] == float("inf")


def test_resolve_latency_bucket_bounds_invalid_defaults() -> None:
    key, bounds = resolve_latency_bucket_bounds("default")
    assert key == "default"
    assert bounds[-1] == float("inf")

    try:
        resolve_latency_bucket_bounds("unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for unknown preset")


def test_latency_bucket_presets_include_micro() -> None:
    assert "micro" in LATENCY_BUCKET_PRESETS_MS
    assert 0.001 in LATENCY_BUCKET_PRESETS_MS["micro"]
