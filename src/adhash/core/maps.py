from __future__ import annotations

import logging
import math
import pickle
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, TYPE_CHECKING

from adhash.io.snapshot import load_snapshot_any, open_snapshot_for_write

if TYPE_CHECKING:  # pragma: no cover
    from adhash.metrics import Metrics


logger = logging.getLogger("hashmap_cli")

_HASH_GOLDEN_64: int = 0x9E3779B97F4A7C15


def _next_power_of_two(value: int) -> int:
    if value <= 1:
        return 1
    return 1 << (value - 1).bit_length()


@dataclass
class _Entry:
    key: Any
    value: Any


class TwoLevelChainingMap:
    """Hash map with two-level chaining buckets."""

    __slots__ = ("M", "G", "_buckets", "_size")

    def __init__(self, initial_buckets: int = 64, groups_per_bucket: int = 8) -> None:
        if initial_buckets < 1 or (initial_buckets & (initial_buckets - 1)) != 0:
            raise ValueError("initial_buckets must be a power of two")
        if groups_per_bucket < 1 or (groups_per_bucket & (groups_per_bucket - 1)) != 0:
            raise ValueError("groups_per_bucket must be a power of two")
        self.M = initial_buckets
        self.G = groups_per_bucket
        self._buckets: List[List[List[_Entry]]] = [[[] for _ in range(self.G)] for _ in range(self.M)]
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def _h1(self, key: Any) -> int:
        return hash(key)

    def _h2(self, key: Any) -> int:
        x = hash((key, _HASH_GOLDEN_64))
        return x ^ (x >> 16)

    def _index_group(self, key: Any) -> Tuple[int, int]:
        i = self._h1(key) & (self.M - 1)
        g = self._h2(key) & (self.G - 1)
        return i, g

    def load_factor(self) -> float:
        return self._size / self.M if self.M else 0.0

    def _rehash(self, new_M: int) -> None:
        old = self._buckets
        self.M = new_M
        self._buckets = [[[] for _ in range(self.G)] for _ in range(self.M)]
        for groups in old:
            for grp in groups:
                for entry in grp:
                    i, g = self._index_group(entry.key)
                    self._buckets[i][g].append(entry)

    def put(self, key: Any, value: Any) -> None:
        i, g = self._index_group(key)
        grp = self._buckets[i][g]
        for entry in grp:
            if entry.key == key:
                entry.value = value
                return
        grp.append(_Entry(key, value))
        self._size += 1
        if self.load_factor() > 0.8:
            self._rehash(self.M * 2)

    def get(self, key: Any) -> Optional[Any]:
        i, g = self._index_group(key)
        for entry in self._buckets[i][g]:
            if entry.key == key:
                return entry.value
        return None

    def delete(self, key: Any) -> bool:
        i, g = self._index_group(key)
        grp = self._buckets[i][g]
        for idx, entry in enumerate(grp):
            if entry.key == key:
                grp[idx] = grp[-1]
                grp.pop()
                self._size -= 1
                return True
        return False

    def items(self) -> Iterator[Tuple[Any, Any]]:
        for groups in self._buckets:
            for grp in groups:
                for entry in grp:
                    yield entry.key, entry.value

    def max_group_len(self) -> int:
        longest = 0
        for groups in self._buckets:
            for grp in groups:
                longest = max(longest, len(grp))
        return longest

    def save(self, filepath: str, compress: bool = False) -> None:
        with open_snapshot_for_write(filepath, compress) as fh:
            pickle.dump(self, fh)

    @staticmethod
    def load(filepath: str) -> "TwoLevelChainingMap":
        obj = load_snapshot_any(filepath)
        if not isinstance(obj, TwoLevelChainingMap):
            raise TypeError("Snapshot is not a TwoLevelChainingMap")
        return obj


class _Tombstone:
    __slots__ = ()


_TOMBSTONE = _Tombstone()


@dataclass
class _RHEntry:
    key: Any
    value: Any


class RobinHoodMap:
    """Open-addressing hash map with Robin Hood probing."""

    __slots__ = ("_table", "_size", "_cap", "_mask", "_tombstones")

    def __init__(self, initial_capacity: int = 64) -> None:
        if initial_capacity < 1 or (initial_capacity & (initial_capacity - 1)) != 0:
            raise ValueError("initial_capacity must be a power of two")
        self._cap = initial_capacity
        self._mask = initial_capacity - 1
        self._table: List[Optional[Any]] = [None] * initial_capacity
        self._size = 0
        self._tombstones = 0

    def __len__(self) -> int:
        return self._size

    def load_factor(self) -> float:
        return self._size / self._cap if self._cap else 0.0

    def tombstone_ratio(self) -> float:
        return (self._tombstones / self._cap) if self._cap else 0.0

    def _idx(self, h: int) -> int:
        return h & self._mask

    def _probe_distance(self, ideal_idx: int, cur_idx: int) -> int:
        return cur_idx - ideal_idx if cur_idx >= ideal_idx else (cur_idx + self._cap) - ideal_idx

    def _resize(self, new_cap: int) -> None:
        old = self._table
        self._cap = new_cap
        self._mask = new_cap - 1
        self._table = [None] * new_cap
        self._size = 0
        self._tombstones = 0
        for slot in old:
            if isinstance(slot, _RHEntry):
                self.put(slot.key, slot.value)

    def compact(self) -> None:
        self._resize(self._cap)

    def put(self, key: Any, value: Any) -> None:
        if self.load_factor() > 0.85:
            self._resize(self._cap * 2)
        h = hash(key)
        idx = self._idx(h)
        cur = _RHEntry(key, value)
        dist = 0
        while True:
            slot = self._table[idx]
            if slot is None:
                self._table[idx] = cur
                self._size += 1
                return
            if slot is _TOMBSTONE:
                self._table[idx] = cur
                self._size += 1
                self._tombstones -= 1
                return
            if slot.key == key:
                slot.value = value
                return
            ideal = self._idx(hash(slot.key))
            slot_dist = self._probe_distance(ideal, idx)
            if slot_dist < dist:
                self._table[idx], cur = cur, slot
                dist = slot_dist
            idx = (idx + 1) & self._mask
            dist += 1

    def get(self, key: Any) -> Optional[Any]:
        h = hash(key)
        idx = self._idx(h)
        scanned = 0
        while scanned <= self._cap:
            slot = self._table[idx]
            if slot is None:
                return None
            if isinstance(slot, _RHEntry) and slot.key == key:
                return slot.value
            idx = (idx + 1) & self._mask
            scanned += 1
        return None

    def delete(self, key: Any) -> bool:
        h = hash(key)
        idx = self._idx(h)
        scanned = 0
        while scanned <= self._cap:
            slot = self._table[idx]
            if slot is None:
                return False
            if isinstance(slot, _RHEntry) and slot.key == key:
                self._table[idx] = _TOMBSTONE
                self._size -= 1
                self._tombstones += 1
                return True
            idx = (idx + 1) & self._mask
            scanned += 1
        return False

    def items(self) -> Iterator[Tuple[Any, Any]]:
        for slot in self._table:
            if isinstance(slot, _RHEntry):
                yield slot.key, slot.value

    def avg_probe_estimate(self, step: int = 8) -> float:
        if self._size == 0:
            return 0.0
        total = 0
        cnt = 0
        for i in range(0, self._cap, step):
            slot = self._table[i]
            if isinstance(slot, _RHEntry):
                ideal = self._idx(hash(slot.key))
                total += self._probe_distance(ideal, i)
                cnt += 1
        return total / max(cnt, 1)

    def save(self, filepath: str, compress: bool = False) -> None:
        with open_snapshot_for_write(filepath, compress) as fh:
            pickle.dump(self, fh)

    @staticmethod
    def load(filepath: str) -> "RobinHoodMap":
        obj = load_snapshot_any(filepath)
        if not isinstance(obj, RobinHoodMap):
            raise TypeError("Snapshot is not a RobinHoodMap")
        return obj


@dataclass
class AdaptiveConfig:
    max_lf_chaining: float = 0.82
    max_group_len: int = 8
    max_avg_probe_robinhood: float = 6.0
    max_tombstone_ratio: float = 0.25
    initial_buckets: int = 64
    groups_per_bucket: int = 8
    initial_capacity_rh: int = 64
    start_backend: str = "chaining"
    incremental_batch: int = 2048
    large_map_warn_threshold: int = 1_000_000
    on_migration: Optional[Callable[[str, str], None]] = None
    on_compaction: Optional[Callable[[], None]] = None


def _cfg_to_picklable_dict(cfg: AdaptiveConfig) -> Dict[str, Any]:
    data = asdict(cfg)
    data["on_migration"] = None
    data["on_compaction"] = None
    return data


def _cfg_from_dict(d: Dict[str, Any]) -> AdaptiveConfig:
    keys = {k: d[k] for k in d.keys() if k in AdaptiveConfig().__dict__.keys()}
    return AdaptiveConfig(**keys)


class HybridAdaptiveHashMap:
    """Adaptive hash map that migrates between chaining and Robin Hood backends."""

    def __init__(self, cfg: AdaptiveConfig = AdaptiveConfig()) -> None:
        self.cfg = cfg
        if cfg.start_backend == "chaining":
            self._backend: Any = TwoLevelChainingMap(cfg.initial_buckets, cfg.groups_per_bucket)
            self._name = "chaining"
        else:
            self._backend = RobinHoodMap(cfg.initial_capacity_rh)
            self._name = "robinhood"
        self._migrating_to: Optional[str] = None
        self._migrate_target: Optional[Any] = None
        self._migrate_iter: Optional[Iterator[Tuple[Any, Any]]] = None
        logger.info("Adaptive map started on %s", self._name)

    def __len__(self) -> int:
        return len(self._backend)

    def backend_name(self) -> str:
        return f"{self._name} -> {self._migrating_to} (migrating)" if self._migrating_to else self._name

    def __getstate__(self) -> Dict[str, Any]:
        while self._migrating_to:
            self._drain_migration()
        return {
            "name": self._name,
            "backend": self._backend,
            "cfg": _cfg_to_picklable_dict(self.cfg),
        }

    def __setstate__(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict) or "backend" not in state or "name" not in state:
            raise TypeError("Bad pickle for HybridAdaptiveHashMap")
        cfg_dict = state.get("cfg", {})
        self.cfg = _cfg_from_dict(cfg_dict) if isinstance(cfg_dict, dict) else AdaptiveConfig()
        self._backend = state["backend"]
        self._name = state["name"]
        self._migrating_to = None
        self._migrate_target = None
        self._migrate_iter = None
        logger.info("Adaptive map restored from pickle (backend=%s)", self._name)

    def backend(self) -> Any:
        while self._migrating_to:
            self._drain_migration()
        return self._backend

    def _begin_migration(self, target: str) -> None:
        size_est = len(self._backend)
        if size_est >= self.cfg.large_map_warn_threshold:
            logger.warning("Large map migration starting (size=%d, target=%s)", size_est, target)
        if target == "robinhood":
            self._migrating_to = target
            capacity_hint = max(self.cfg.initial_capacity_rh, len(self._backend) or 1)
            rounded = _next_power_of_two(capacity_hint)
            if rounded != capacity_hint:
                logger.warning(
                    "Rounded RobinHood migration capacity from %d to %d (power-of-two requirement)",
                    capacity_hint,
                    rounded,
                )
            self._migrate_target = RobinHoodMap(rounded)
        else:
            self._migrating_to = target
            self._migrate_target = TwoLevelChainingMap(self.cfg.initial_buckets, self.cfg.groups_per_bucket)
        self._migrate_iter = iter(self._backend.items())
        logger.info("Migration started: %s -> %s", self._name, target)

    def _drain_migration(self) -> None:
        if not self._migrating_to or self._migrate_target is None or self._migrate_iter is None:
            return
        migrated = 0
        assert self._migrate_iter is not None
        target = self._migrate_target
        for _ in range(self.cfg.incremental_batch):
            try:
                k, v = next(self._migrate_iter)
            except StopIteration:
                self._backend = target
                old = self._name
                self._name = self._migrating_to
                self._migrating_to = None
                self._migrate_target = None
                self._migrate_iter = None
                logger.info("Migration complete. Now on backend=%s", self._name)
                if self.cfg.on_migration:
                    try:
                        self.cfg.on_migration(old, self._name)
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("on_migration callback failed")
                return
            target.put(k, v)
            migrated += 1
        logger.debug("Migrated %d entries (target=%s)", migrated, self._migrating_to)

    def _maintenance(self) -> None:
        self._drain_migration()
        if self._migrating_to:
            return
        if isinstance(self._backend, TwoLevelChainingMap):
            lf = self._backend.load_factor()
            mg = self._backend.max_group_len()
            if lf > self.cfg.max_lf_chaining or mg > self.cfg.max_group_len:
                self._begin_migration("robinhood")
        elif isinstance(self._backend, RobinHoodMap):
            ap = self._backend.avg_probe_estimate()
            if ap > self.cfg.max_avg_probe_robinhood:
                self._begin_migration("chaining")
            elif self._backend.tombstone_ratio() > self.cfg.max_tombstone_ratio:
                logger.info("Auto-compacting RobinHoodMap (tombstone_ratio=%.3f)", self._backend.tombstone_ratio())
                self._backend.compact()
                if self.cfg.on_compaction:
                    try:
                        self.cfg.on_compaction()
                    except Exception:  # pragma: no cover
                        logger.exception("on_compaction callback failed")

    def put(self, key: Any, value: Any) -> None:
        self._drain_migration()
        (self._migrate_target or self._backend).put(key, value)
        self._maintenance()

    def get(self, key: Any) -> Optional[Any]:
        self._drain_migration()
        if self._migrate_target is not None:
            value = self._migrate_target.get(key)
            if value is not None:
                return value
        return self._backend.get(key)

    def delete(self, key: Any) -> bool:
        self._drain_migration()
        if self._migrate_target is not None and self._migrate_target.delete(key):
            return True
        removed = self._backend.delete(key)
        self._maintenance()
        return removed

    def items(self) -> Iterable[Tuple[Any, Any]]:
        while self._migrating_to:
            self._drain_migration()
        return self._backend.items()

    def save(self, filepath: str, compress: bool = False) -> None:
        while self._migrating_to:
            self._drain_migration()
        state = {
            "name": self._name,
            "backend": self._backend,
            "cfg": _cfg_to_picklable_dict(self.cfg),
        }
        with open_snapshot_for_write(filepath, compress) as fh:
            pickle.dump(state, fh)

    @staticmethod
    def load(filepath: str) -> "HybridAdaptiveHashMap":
        state = load_snapshot_any(filepath)
        if isinstance(state, HybridAdaptiveHashMap):
            return state
        if not isinstance(state, dict) or "backend" not in state or "name" not in state:
            raise TypeError("Snapshot is not a HybridAdaptiveHashMap")
        cfg_dict = state.get("cfg", {})
        cfg = _cfg_from_dict(cfg_dict) if isinstance(cfg_dict, dict) else AdaptiveConfig()
        obj = HybridAdaptiveHashMap(cfg)
        obj._backend = state["backend"]
        obj._name = state["name"]
        obj._migrating_to = None
        obj._migrate_target = None
        obj._migrate_iter = None
        return obj


class MetricsSink:
    """Bridge map lifecycle events into Metrics counters and event logs."""

    def __init__(
        self,
        metrics: Optional["Metrics"],
        events: Optional[List[Dict[str, Any]]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.metrics = metrics
        self.events = events
        self.clock = clock or (lambda: 0.0)

    def inc_migrations(self) -> None:
        if self.metrics:
            self.metrics.migrations_total += 1

    def inc_compactions(self) -> None:
        if self.metrics:
            self.metrics.compactions_total += 1

    def record_event(self, kind: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self.events is None:
            return
        event = {"type": kind, "t": self.clock()}
        if payload:
            event.update(payload)
        self.events.append(event)

    def attach(self, m: Any) -> None:
        if isinstance(m, HybridAdaptiveHashMap):
            def on_migration(old: str, new: str) -> None:
                self.inc_migrations()
                self.record_event("switch", {"from": old, "to": new})

            def on_compaction() -> None:
                self.inc_compactions()
                self.record_event("compaction", {"backend": m.backend_name()})

            m.cfg.on_migration = on_migration
            m.cfg.on_compaction = on_compaction


def reattach_runtime_callbacks(m: Any, sink: MetricsSink) -> None:
    """Reattach metrics hooks for adaptive maps restored from snapshots."""

    sink.attach(m)


def sample_metrics(m: Any, metrics: "Metrics") -> None:
    metrics.backend_name = getattr(m, "backend_name", lambda: type(m).__name__)()
    metrics.load_factor = 0.0
    metrics.max_group_len = 0.0
    metrics.avg_probe_estimate = 0.0
    metrics.tombstone_ratio = 0.0
    if isinstance(m, TwoLevelChainingMap):
        metrics.load_factor = m.load_factor()
        metrics.max_group_len = float(m.max_group_len())
    elif isinstance(m, RobinHoodMap):
        metrics.load_factor = m.load_factor()
        metrics.avg_probe_estimate = float(m.avg_probe_estimate())
        metrics.tombstone_ratio = float(m.tombstone_ratio())
    elif isinstance(m, HybridAdaptiveHashMap):
        metrics.backend_name = m.backend_name()
        backend = getattr(m, "_backend", None)
        if isinstance(backend, TwoLevelChainingMap):
            metrics.load_factor = backend.load_factor()
            metrics.max_group_len = float(backend.max_group_len())
        elif isinstance(backend, RobinHoodMap):
            metrics.load_factor = backend.load_factor()
            metrics.avg_probe_estimate = float(backend.avg_probe_estimate())
            metrics.tombstone_ratio = float(backend.tombstone_ratio())


def collect_probe_histogram(m: Any) -> List[List[int]]:
    histogram: Dict[int, int] = defaultdict(int)

    def record(rh: RobinHoodMap) -> None:
        for idx, slot in enumerate(rh._table):  # type: ignore[attr-defined]
            if isinstance(slot, _RHEntry):
                ideal = rh._idx(hash(slot.key))
                dist = rh._probe_distance(ideal, idx)
                histogram[int(dist)] += 1

    if isinstance(m, RobinHoodMap):
        record(m)
    elif isinstance(m, HybridAdaptiveHashMap):
        backend = getattr(m, "_backend", None)
        if isinstance(backend, RobinHoodMap):
            record(backend)
    return [[distance, count] for distance, count in sorted(histogram.items())]


def collect_key_heatmap(m: Any, target_cols: int = 32, max_cells: int = 512) -> Dict[str, Any]:
    def key_counts_for_map(obj: Any) -> List[int]:
        if isinstance(obj, TwoLevelChainingMap):
            return [len(group) for bucket in obj._buckets for group in bucket]  # type: ignore[attr-defined]
        if isinstance(obj, RobinHoodMap):
            return [1 if isinstance(slot, _RHEntry) else 0 for slot in obj._table]  # type: ignore[attr-defined]
        if isinstance(obj, HybridAdaptiveHashMap):
            backend = getattr(obj, "_backend", None)
            if backend is not None:
                return key_counts_for_map(backend)
        return []

    base_counts = key_counts_for_map(m)
    original_slots = len(base_counts)
    if not base_counts:
        return {
            "rows": 0,
            "cols": 0,
            "matrix": [],
            "max": 0,
            "total": 0,
            "slot_span": 1,
            "original_slots": original_slots,
        }

    total = sum(base_counts)
    target_cells = max(1, max_cells)
    group_width = max(1, math.ceil(original_slots / target_cells))
    aggregated: List[int] = []
    for idx in range(0, original_slots, group_width):
        aggregated.append(sum(base_counts[idx : idx + group_width]))

    cols = max(1, min(target_cols, len(aggregated)))
    rows = math.ceil(len(aggregated) / cols)
    padded_length = rows * cols
    if len(aggregated) < padded_length:
        aggregated.extend([0] * (padded_length - len(aggregated)))
    matrix = [aggregated[r * cols : (r + 1) * cols] for r in range(rows)]

    return {
        "rows": rows,
        "cols": cols,
        "matrix": matrix,
        "max": max(aggregated) if aggregated else 0,
        "total": total,
        "slot_span": group_width,
        "original_slots": original_slots,
    }


__all__ = [
    "AdaptiveConfig",
    "HybridAdaptiveHashMap",
    "MetricsSink",
    "RobinHoodMap",
    "TwoLevelChainingMap",
    "collect_key_heatmap",
    "collect_probe_histogram",
    "reattach_runtime_callbacks",
    "sample_metrics",
]
