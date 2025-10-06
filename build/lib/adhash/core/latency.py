from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple


DEFAULT_LATENCY_BUCKET_BOUNDS_MS: Tuple[float, ...] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    math.inf,
)

MICRO_LATENCY_BUCKET_BOUNDS_MS: Tuple[float, ...] = (
    0.001,
    0.002,
    0.005,
    0.01,
    0.02,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.0,
    5.0,
    10.0,
    math.inf,
)

LATENCY_BUCKET_PRESETS_MS: Dict[str, Tuple[float, ...]] = {
    "default": DEFAULT_LATENCY_BUCKET_BOUNDS_MS,
    "micro": MICRO_LATENCY_BUCKET_BOUNDS_MS,
}


def resolve_latency_bucket_bounds(name: str) -> Tuple[str, Tuple[float, ...]]:
    """Return canonical preset key + bounds for latency histograms."""

    key = (name or "default").strip().lower()
    preset = LATENCY_BUCKET_PRESETS_MS.get(key)
    if preset is None:
        raise ValueError(f"Unknown latency bucket preset: {name}")
    return key, preset


class Reservoir:
    """Fixed-size reservoir with uniform random replacement."""

    __slots__ = ("k", "buf", "n", "rng")

    def __init__(self, k: int = 1000, seed: int = 0xC0FFEE) -> None:
        self.k = max(1, k)
        self.buf: List[float] = []
        self.n = 0
        self.rng = random.Random(seed)

    def offer(self, value_ms: float) -> None:
        self.n += 1
        if len(self.buf) < self.k:
            self.buf.append(value_ms)
            return
        j = self.rng.randrange(self.n)
        if j < self.k:
            self.buf[j] = value_ms

    def percentiles(self, ps: List[float]) -> Dict[str, float]:
        if not self.buf:
            return {f"p{int(p * 100)}": 0.0 for p in ps}
        data = sorted(self.buf)
        out: Dict[str, float] = {}
        for p in ps:
            idx = min(len(data) - 1, max(0, int(round(p * (len(data) - 1)))))
            out[f"p{int(p * 100)}"] = data[idx]
        return out


__all__ = [
    "DEFAULT_LATENCY_BUCKET_BOUNDS_MS",
    "MICRO_LATENCY_BUCKET_BOUNDS_MS",
    "LATENCY_BUCKET_PRESETS_MS",
    "Reservoir",
    "resolve_latency_bucket_bounds",
]
