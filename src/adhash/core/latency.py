from __future__ import annotations

import hashlib
import math
import secrets
from collections.abc import Callable
from typing import cast

DEFAULT_LATENCY_BUCKET_BOUNDS_MS: tuple[float, ...] = (
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

MICRO_LATENCY_BUCKET_BOUNDS_MS: tuple[float, ...] = (
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

LATENCY_BUCKET_PRESETS_MS: dict[str, tuple[float, ...]] = {
    "default": DEFAULT_LATENCY_BUCKET_BOUNDS_MS,
    "micro": MICRO_LATENCY_BUCKET_BOUNDS_MS,
}


def resolve_latency_bucket_bounds(name: str) -> tuple[str, tuple[float, ...]]:
    """Return canonical preset key + bounds for latency histograms."""

    key = (name or "default").strip().lower()
    preset = LATENCY_BUCKET_PRESETS_MS.get(key)
    if preset is None:
        raise ValueError(f"Unknown latency bucket preset: {name}")
    return key, preset


class _ReservoirRNG:
    """Deterministic RNG that avoids the insecure ``random`` module defaults."""

    __slots__ = ("_system_random", "_seed_material", "_counter", "_derive_bytes")

    def __init__(self, seed: int | None = None) -> None:
        self._derive_bytes: Callable[[int], int]
        self._system_random: secrets.SystemRandom | None
        self._seed_material: bytes | None
        if seed is None:
            self._system_random = secrets.SystemRandom()
            self._seed_material = None
            self._counter = 0
            self._derive_bytes = cast(Callable[[int], int], self._system_random.getrandbits)
        else:
            seed_bytes = str(seed).encode("utf-8")
            self._system_random = None
            self._seed_material = hashlib.blake2s(seed_bytes).digest()
            self._counter = 0
            self._derive_bytes = self._deterministic_bits

    def _deterministic_bits(self, bits: int) -> int:
        """Return a deterministic integer in [0, 2**bits)."""

        if self._seed_material is None:
            raise RuntimeError("Deterministic generator requires seed material")
        self._counter += 1
        counter_bytes = self._counter.to_bytes(16, "big", signed=False)
        digest = hashlib.blake2s(self._seed_material + counter_bytes).digest()
        value = int.from_bytes(digest[: bits // 8], "big")
        # Ensure we have enough entropy even if bits < 64
        if bits % 8:
            extra = digest[bits // 8]
            value = (value << (bits % 8)) | (extra >> (8 - (bits % 8)))
        upper_bound = 1 << bits
        return value % upper_bound

    def randrange(self, stop: int) -> int:
        if stop <= 0:
            raise ValueError("Upper bound must be positive")
        bits = max(1, stop.bit_length())
        while True:
            value = self._derive_bytes(bits)
            if value < stop:
                return value


class Reservoir:
    """Fixed-size reservoir with uniform random replacement."""

    __slots__ = ("k", "buf", "n", "rng")

    def __init__(self, k: int = 1000, seed: int | None = 0xC0FFEE) -> None:
        self.k = max(1, k)
        self.buf: list[float] = []
        self.n = 0
        self.rng = _ReservoirRNG(seed)

    def offer(self, value_ms: float) -> None:
        self.n += 1
        if len(self.buf) < self.k:
            self.buf.append(value_ms)
            return
        j = self.rng.randrange(self.n)
        if j < self.k:
            self.buf[j] = value_ms

    def percentiles(self, ps: list[float]) -> dict[str, float]:
        if not self.buf:
            return {f"p{int(p * 100)}": 0.0 for p in ps}
        data = sorted(self.buf)
        out: dict[str, float] = {}
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
