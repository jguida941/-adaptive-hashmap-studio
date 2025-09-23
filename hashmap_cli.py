#!/usr/bin/env python3
"""
hashmap_cli.py

A production-grade, single-file toolkit:
- TwoLevelChainingMap (2-level chaining, cache-friendly)
- RobinHoodMap (open addressing with Robin Hood displacement; tombstone-aware)
- HybridAdaptiveHashMap (adaptive: monitors health, migrates incrementally)
- Profiler, synthetic workload generator (Zipf + adversarial), CSV runner
- Prometheus-style /metrics + zero-dependency dashboard
- Snapshots (pickle) with optional gzip compression (.gz or --compress)
- Proactive compaction tick (--compact-interval)
- Offline snapshot compaction for Robin Hood
- Snapshot verification (invariants) + --repair (safe compaction)
- CI JSON summary with throughput and percentile latencies (reservoir sampling)

New in this version:
  * Snapshot serialization hardened:
      - Callbacks (on_migration/on_compaction) are **not pickled**. Config is saved as a plain dict.
  * run-csv:
      --json-summary-out FILE
      --latency-sample-k K (default 1000)
      --latency-sample-every N (default 128)
      -> adds p50/p90/p99 latency (ms) for overall **and per op**: put/get/del
  * Observability:
      - Added hashmap_compactions_total counter (metrics + JSON)
  * Reliability:
      - Metrics server shuts down via try/finally even on errors.
"""

from __future__ import annotations

import argparse
import csv
import os
import gzip
import json
import logging
import pickle
import random
import sys
import threading
import time
from dataclasses import dataclass, asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple

# --------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------
logger = logging.getLogger("hashmap_cli")
if not logger.handlers:
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(sh)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------
# Compressed pickle I/O helpers
# --------------------------------------------------------------------
def _open_for_read(path: str):
    """Open a snapshot for reading (auto-detect .gz)."""
    return gzip.open(path, "rb") if path.endswith(".gz") else open(path, "rb")

def _open_for_write(path: str, compress: bool):
    """Open a snapshot for writing; gzip if --compress or .gz suffix."""
    use_gz = compress or path.endswith(".gz")
    return gzip.open(path, "wb") if use_gz else open(path, "wb")

# --------------------------------------------------------------------
# Shared constants
# --------------------------------------------------------------------
_HASH_GOLDEN_64: int = 0x9E3779B97F4A7C15  # golden-ratio mixer for second hash

# --------------------------------------------------------------------
# Two-level chaining backend
# --------------------------------------------------------------------
@dataclass
class _Entry:
    key: Any
    value: Any

class TwoLevelChainingMap:
    """
    Hash map with 2-level chaining: M buckets, each with G small vectors.
    Insert: append; Delete: swap-pop; Rehash when LF>0.8
    """
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

    def __len__(self) -> int: return self._size

    def _h1(self, key: Any) -> int: return hash(key)

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
                for e in grp:
                    i, g = self._index_group(e.key)
                    self._buckets[i][g].append(e)

    def put(self, key: Any, value: Any) -> None:
        i, g = self._index_group(key)
        grp = self._buckets[i][g]
        for e in grp:
            if e.key == key:
                e.value = value
                return
        grp.append(_Entry(key, value))
        self._size += 1
        if self.load_factor() > 0.8:
            self._rehash(self.M * 2)

    def get(self, key: Any) -> Optional[Any]:
        i, g = self._index_group(key)
        for e in self._buckets[i][g]:
            if e.key == key:
                return e.value
        return None

    def delete(self, key: Any) -> bool:
        i, g = self._index_group(key)
        grp = self._buckets[i][g]
        for idx, e in enumerate(grp):
            if e.key == key:
                grp[idx] = grp[-1]
                grp.pop()
                self._size -= 1
                return True
        return False

    def items(self) -> Iterator[Tuple[Any, Any]]:
        for groups in self._buckets:
            for grp in groups:
                for e in grp:
                    yield e.key, e.value

    def max_group_len(self) -> int:
        mg = 0
        for groups in self._buckets:
            for grp in groups:
                if len(grp) > mg:
                    mg = len(grp)
        return mg

    # Snapshot
    def save(self, filepath: str, compress: bool = False) -> None:
        with _open_for_write(filepath, compress) as f:
            pickle.dump(self, f)

    @staticmethod
    def load(filepath: str) -> "TwoLevelChainingMap":
        with _open_for_read(filepath) as f:
            obj = pickle.load(f)
        if not isinstance(obj, TwoLevelChainingMap):
            raise TypeError("Snapshot is not a TwoLevelChainingMap")
        return obj

# --------------------------------------------------------------------
# Robin Hood backend
# --------------------------------------------------------------------
class _Tombstone: __slots__ = ()
_TOMBSTONE = _Tombstone()

@dataclass
class _RHEntry:
    key: Any
    value: Any

class RobinHoodMap:
    """
    Robin Hood linear probing with tombstones and compaction.
    Ensures bounded scans by checking up to _cap slots on get/delete.
    """
    __slots__ = ("_table", "_size", "_cap", "_mask", "_tombstones")

    def __init__(self, initial_capacity: int = 64) -> None:
        if initial_capacity < 1 or (initial_capacity & (initial_capacity - 1)) != 0:
            raise ValueError("initial_capacity must be a power of two")
        self._cap = initial_capacity
        self._mask = initial_capacity - 1
        self._table: List[Optional[Any]] = [None] * initial_capacity
        self._size = 0
        self._tombstones = 0

    def __len__(self) -> int: return self._size
    def load_factor(self) -> float: return self._size / self._cap if self._cap else 0.0
    def tombstone_ratio(self) -> float: return (self._tombstones / self._cap) if self._cap else 0.0

    def _idx(self, h: int) -> int: return h & self._mask

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
        """Purge tombstones and rebuild at same capacity."""
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

    # Snapshot
    def save(self, filepath: str, compress: bool = False) -> None:
        with _open_for_write(filepath, compress) as f:
            pickle.dump(self, f)

    @staticmethod
    def load(filepath: str) -> "RobinHoodMap":
        with _open_for_read(filepath) as f:
            obj = pickle.load(f)
        if not isinstance(obj, RobinHoodMap):
            raise TypeError("Snapshot is not a RobinHoodMap")
        return obj

# --------------------------------------------------------------------
# Metrics + dashboard
# --------------------------------------------------------------------
class Metrics:
    def __init__(self) -> None:
        self.ops_total = 0
        self.puts_total = 0
        self.gets_total = 0
        self.dels_total = 0
        self.migrations_total = 0
        self.compactions_total = 0  # NEW
        self.load_factor = 0.0
        self.max_group_len = 0.0
        self.avg_probe_estimate = 0.0
        self.backend_name = "unknown"

    def render(self) -> str:
        return "\n".join([
            "# HELP hashmap_ops_total Total operations processed",
            "# TYPE hashmap_ops_total counter",
            f"hashmap_ops_total {self.ops_total}",
            "# HELP hashmap_puts_total Total put operations",
            "# TYPE hashmap_puts_total counter",
            f"hashmap_puts_total {self.puts_total}",
            "# HELP hashmap_gets_total Total get operations",
            "# TYPE hashmap_gets_total counter",
            f"hashmap_gets_total {self.gets_total}",
            "# HELP hashmap_dels_total Total delete operations",
            "# TYPE hashmap_dels_total counter",
            f"hashmap_dels_total {self.dels_total}",
            "# HELP hashmap_migrations_total Backend migrations",
            "# TYPE hashmap_migrations_total counter",
            f"hashmap_migrations_total {self.migrations_total}",
            "# HELP hashmap_compactions_total Backend compactions",
            "# TYPE hashmap_compactions_total counter",
            f"hashmap_compactions_total {self.compactions_total}",
            "# HELP hashmap_load_factor Current load factor",
            "# TYPE hashmap_load_factor gauge",
            f"hashmap_load_factor {self.load_factor:.6f}",
            "# HELP hashmap_max_group_len Max inner group length (chaining)",
            "# TYPE hashmap_max_group_len gauge",
            f"hashmap_max_group_len {self.max_group_len:.6f}",
            "# HELP hashmap_avg_probe_estimate Estimated avg probe distance (robinhood)",
            "# TYPE hashmap_avg_probe_estimate gauge",
            f"hashmap_avg_probe_estimate {self.avg_probe_estimate:.6f}",
            "# HELP hashmap_backend_info Backend in use (label)",
            "# TYPE hashmap_backend_info gauge",
            f'hashmap_backend_info{{name="{self.backend_name}"}} 1',
        ]) + "\n"

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>Adaptive HashMap Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
body{font-family:system-ui,Arial,sans-serif;margin:24px}
h1{margin:0 0 12px}
.card{border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0}
.row{display:flex;gap:12px;flex-wrap:wrap}
.row .card{flex:1 1 300px}
code{background:#f6f8fa;padding:2px 6px;border-radius:4px}
</style>
</head><body>
<h1>Adaptive HashMap Dashboard</h1>
<p>Polling <code>/metrics</code> every 2s. Backend: <strong id="backend">-</strong></p>
<div class="row">
  <div class="card"><canvas id="lf"></canvas></div>
  <div class="card"><canvas id="mgl"></canvas></div>
  <div class="card"><canvas id="ape"></canvas></div>
</div>
<div class="card">
  <div>Ops: <span id="ops">0</span>, Puts: <span id="puts">0</span>,
  Gets: <span id="gets">0</span>, Dels: <span id="dels">0</span>,
  Migrations: <span id="migs">0</span></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const ids=['lf','mgl','ape'], charts={};
function mk(id){return new Chart(document.getElementById(id),{type:'line',data:{labels:[],datasets:[{label:id,data:[]}]},options:{animation:false,responsive:true,scales:{y:{beginAtZero:true}}}})}
ids.forEach(id=>charts[id]=mk(id));
function upChart(id,val){const c=charts[id],d=c.data,t=new Date().toLocaleTimeString();d.labels.push(t);d.datasets[0].data.push(val);if(d.labels.length>60){d.labels.shift();d.datasets[0].data.shift();}c.update();}
async function poll(){try{const r=await fetch('/metrics');const txt=await r.text();
const m=Object.fromEntries([...txt.matchAll(/^(\\w+)\\s+([0-9.]+)$/mg)].map(x=>[x[1],parseFloat(x[2])]));
const be=txt.match(/hashmap_backend_info\\{name="([^"]+)"\\}\\s+1/);document.getElementById('backend').textContent=be?be[1]:'unknown';
document.getElementById('ops').textContent=m.hashmap_ops_total||0;document.getElementById('puts').textContent=m.hashmap_puts_total||0;
document.getElementById('gets').textContent=m.hashmap_gets_total||0;document.getElementById('dels').textContent=m.hashmap_dels_total||0;document.getElementById('migs').textContent=m.hashmap_migrations_total||0;
upChart('lf', m.hashmap_load_factor||0);upChart('mgl', m.hashmap_max_group_len||0);upChart('ape', m.hashmap_avg_probe_estimate||0);}catch(e){} setTimeout(poll,2000);} poll();
</script>
</body></html>
"""

def start_metrics_server(metrics: Metrics, port: int) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/metrics":
                body = metrics.render().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body); return
            if self.path == "/" or self.path.startswith("/index.html"):
                body = _DASHBOARD_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body); return
            self.send_response(404); self.end_headers()
        def log_message(self, fmt: str, *args: Any) -> None: return
    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Metrics server: http://0.0.0.0:%d/  (dashboard) and /metrics", port)
    return server

# --------------------------------------------------------------------
# Adaptive wrapper
# --------------------------------------------------------------------
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
    on_compaction: Optional[Callable[[], None]] = None  # NEW

def _cfg_to_picklable_dict(cfg: AdaptiveConfig) -> Dict[str, Any]:
    """Strip non-picklable callbacks before saving."""
    d = asdict(cfg)
    d["on_migration"] = None
    d["on_compaction"] = None
    return d

def _cfg_from_dict(d: Dict[str, Any]) -> AdaptiveConfig:
    """Rebuild AdaptiveConfig from a dict (callbacks absent)."""
    # Ignore unknown keys to be forward-compatible.
    keys = {k: d[k] for k in d.keys() if k in AdaptiveConfig().__dict__.keys()}
    cfg = AdaptiveConfig(**keys)  # callbacks default to None
    return cfg

class HybridAdaptiveHashMap:
    """
    Adaptive map: monitors health, migrates incrementally between backends.
    Writes during migration go to the target; reads check target then source.
    Auto-compacts RH based on tombstone ratio. Compactions fire on_compaction().
    """
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

    def __len__(self) -> int: return len(self._backend)
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

    # Migration internals
    def _begin_migration(self, target: str) -> None:
        size_est = len(self._backend)
        if size_est >= self.cfg.large_map_warn_threshold:
            logger.warning("Starting migration on large map (size=%d). Batch=%d", size_est, self.cfg.incremental_batch)
        logger.info("Preparing migration: %s -> %s", self._name, target)
        self._migrate_target = (TwoLevelChainingMap(self.cfg.initial_buckets, self.cfg.groups_per_bucket)
                                if target == "chaining" else RobinHoodMap(self.cfg.initial_capacity_rh))
        self._migrate_iter = self._backend.items()
        self._migrating_to = target

    def _drain_migration(self) -> None:
        if not self._migrating_to:
            return
        assert self._migrate_iter is not None and self._migrate_target is not None
        moved = 0
        try:
            while moved < self.cfg.incremental_batch:
                k, v = next(self._migrate_iter)
                self._migrate_target.put(k, v)
                moved += 1
        except StopIteration:
            old = self._name
            self._backend = self._migrate_target
            self._name = self._migrating_to or self._name
            self._migrating_to = None
            self._migrate_target = None
            self._migrate_iter = None
            logger.info("Migration complete. Now on backend=%s", self._name)
            if self.cfg.on_migration:
                try:
                    self.cfg.on_migration(old, self._name)
                except Exception as e:
                    logger.error("on_migration callback raised: %s", e)
        except Exception as e:
            logger.exception("Migration error after moving %d items: %s", moved, e)

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
            else:
                if self._backend.tombstone_ratio() > self.cfg.max_tombstone_ratio:
                    logger.info("Auto-compacting RobinHoodMap (tombstone_ratio=%.3f)", self._backend.tombstone_ratio())
                    self._backend.compact()
                    if self.cfg.on_compaction:
                        try:
                            self.cfg.on_compaction()
                        except Exception as e:
                            logger.error("on_compaction callback raised: %s", e)

    # Public API
    def put(self, k: Any, v: Any) -> None:
        self._drain_migration()
        (self._migrate_target or self._backend).put(k, v)
        self._maintenance()

    def get(self, k: Any) -> Optional[Any]:
        self._drain_migration()
        if self._migrate_target is not None:
            v = self._migrate_target.get(k)
            if v is not None:
                return v
        return self._backend.get(k)

    def delete(self, k: Any) -> bool:
        self._drain_migration()
        if self._migrate_target is not None and self._migrate_target.delete(k):
            return True
        ok = self._backend.delete(k)
        self._maintenance()
        return ok

    def items(self) -> Iterable[Tuple[Any, Any]]:
        while self._migrating_to:
            self._drain_migration()
        return self._backend.items()

    # Snapshot (callbacks stripped)
    def save(self, filepath: str, compress: bool = False) -> None:
        while self._migrating_to:
            self._drain_migration()
        state = {
            "name": self._name,
            "backend": self._backend,
            "cfg": _cfg_to_picklable_dict(self.cfg),  # callbacks removed
        }
        with _open_for_write(filepath, compress) as f:
            pickle.dump(state, f)

    @staticmethod
    def load(filepath: str) -> "HybridAdaptiveHashMap":
        with _open_for_read(filepath) as f:
            state = pickle.load(f)
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
        # Note: callbacks are intentionally not restored from snapshot.
        return obj

# --------------------------------------------------------------------
# Metrics helpers
# --------------------------------------------------------------------
class MetricsSink:
    def __init__(self, metrics: Optional[Metrics]) -> None:
        self.metrics = metrics
    def inc_migrations(self) -> None:
        if self.metrics:
            self.metrics.migrations_total += 1
    def inc_compactions(self) -> None:
        if self.metrics:
            self.metrics.compactions_total += 1

def _reattach_runtime_callbacks(m: Any, metrics: Optional[Metrics]) -> None:
    """Reattach metrics hooks for adaptive maps that come from snapshots."""
    if isinstance(m, HybridAdaptiveHashMap) and metrics is not None:
        sink = MetricsSink(metrics)
        m.cfg.on_migration = lambda _old, _new: sink.inc_migrations()
        m.cfg.on_compaction = lambda: sink.inc_compactions()

def build_map(mode: str, metrics: Optional[Metrics] = None) -> Any:
    sink = MetricsSink(metrics)
    def make_adaptive() -> HybridAdaptiveHashMap:
        cfg = AdaptiveConfig(
            start_backend="chaining",
            initial_buckets=64,
            groups_per_bucket=8,
            initial_capacity_rh=64,
            incremental_batch=2048,
        )
        env_start = os.getenv("ADAPTIVE_START_BACKEND")
        if env_start in ("chaining", "robinhood"):
            cfg.start_backend = env_start
        env_max_lf = os.getenv("ADAPTIVE_MAX_LF_CHAINING")
        if env_max_lf is not None:
            try:
                cfg.max_lf_chaining = float(env_max_lf)
            except ValueError:
                logger.warning("Invalid ADAPTIVE_MAX_LF_CHAINING=%s", env_max_lf)
        env_max_group = os.getenv("ADAPTIVE_MAX_GROUP_LEN")
        if env_max_group is not None:
            try:
                cfg.max_group_len = int(env_max_group)
            except ValueError:
                logger.warning("Invalid ADAPTIVE_MAX_GROUP_LEN=%s", env_max_group)
        env_batch = os.getenv("ADAPTIVE_INCREMENTAL_BATCH")
        if env_batch is not None:
            try:
                cfg.incremental_batch = max(1, int(env_batch))
            except ValueError:
                logger.warning("Invalid ADAPTIVE_INCREMENTAL_BATCH=%s", env_batch)
        m = HybridAdaptiveHashMap(cfg)
        # Reattach callbacks at runtime (not part of snapshot)
        m.cfg.on_migration = lambda _o, _n: sink.inc_migrations()
        m.cfg.on_compaction = lambda: sink.inc_compactions()
        return m
    if mode == "fast-insert":
        return TwoLevelChainingMap(initial_buckets=64, groups_per_bucket=8)
    if mode in ("fast-lookup", "memory-tight"):
        return RobinHoodMap(initial_capacity=64)
    if mode == "adaptive":
        return make_adaptive()
    raise ValueError(f"unknown mode: {mode}")

def sample_metrics(m: Any, metrics: Metrics) -> None:
    metrics.backend_name = getattr(m, "backend_name", lambda: type(m).__name__)()
    metrics.load_factor = 0.0
    metrics.max_group_len = 0.0
    metrics.avg_probe_estimate = 0.0
    if isinstance(m, TwoLevelChainingMap):
        metrics.load_factor = m.load_factor()
        metrics.max_group_len = float(m.max_group_len())
    elif isinstance(m, RobinHoodMap):
        metrics.load_factor = m.load_factor()
        metrics.avg_probe_estimate = float(m.avg_probe_estimate())
    elif isinstance(m, HybridAdaptiveHashMap):
        metrics.backend_name = m.backend_name()
        backend = getattr(m, "_backend", None)
        if isinstance(backend, TwoLevelChainingMap):
            metrics.load_factor = backend.load_factor()
            metrics.max_group_len = float(backend.max_group_len())
        elif isinstance(backend, RobinHoodMap):
            metrics.load_factor = backend.load_factor()
            metrics.avg_probe_estimate = float(backend.avg_probe_estimate())

# --------------------------------------------------------------------
# Reservoir sampling for latency percentiles
# --------------------------------------------------------------------
class Reservoir:
    """
    Fixed-size reservoir with uniform random replacement.
    Stores float milliseconds for sampled operation latencies.
    """
    __slots__ = ("k", "buf", "n", "rng")

    def __init__(self, k: int = 1000, seed: int = 0xC0FFEE) -> None:
        self.k = max(1, k)
        self.buf: List[float] = []
        self.n = 0  # total seen
        self.rng = random.Random(seed)

    def offer(self, value_ms: float) -> None:
        """Offer a sample; replaces random entry after reservoir is full."""
        self.n += 1
        if len(self.buf) < self.k:
            self.buf.append(value_ms)
            return
        j = self.rng.randrange(self.n)
        if j < self.k:
            self.buf[j] = value_ms

    def percentiles(self, ps: List[float]) -> Dict[str, float]:
        """Return percentile map { 'p50': .., 'p90': .., ... } from reservoir."""
        if not self.buf:
            return {f"p{int(p*100)}": 0.0 for p in ps}
        data = sorted(self.buf)
        out: Dict[str, float] = {}
        for p in ps:
            idx = min(len(data) - 1, max(0, int(round(p * (len(data) - 1)))))
            out[f"p{int(p*100)}"] = data[idx]
        return out

# --------------------------------------------------------------------
# Ops runner / profiler / generator
# --------------------------------------------------------------------
def run_op(m: Any, op: str, key: Optional[str], value: Optional[str],
           metrics: Optional[Metrics] = None) -> Optional[str]:
    if op == "put":
        assert key is not None and value is not None
        m.put(key, value)
        if metrics: metrics.puts_total += 1
    elif op == "get":
        assert key is not None
        v = m.get(key)
        if metrics: metrics.gets_total += 1
        return "" if v is None else str(v)
    elif op == "del":
        assert key is not None
        ok = m.delete(key)
        if metrics: metrics.dels_total += 1
        return "1" if ok else "0"
    elif op == "items":
        return "\n".join(f"{k},{v}" for k, v in m.items())
    else:
        raise ValueError(f"unknown op: {op}")
    return "OK"

def profile_csv(path: str, sample_limit: int = 5000) -> str:
    def load_ops():
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            for i, row in enumerate(r):
                if sample_limit and i >= sample_limit: break
                yield row["op"], row["key"], row.get("value") or None
    ops = list(load_ops())
    candidates: Dict[str, Any] = {
        "fast-insert": build_map("fast-insert"),
        "fast-lookup": build_map("fast-lookup"),
    }
    results: Dict[str, float] = {}
    for label, impl in candidates.items():
        start = time.perf_counter()
        for op, k, v in ops:
            if op == "items": continue
            run_op(impl, op, k, v)
        elapsed = time.perf_counter() - start
        results[label] = elapsed
        logger.info("Profile %s: %.6f s over %d ops", label, elapsed, len(ops))
    pick = min(results, key=results.get)
    logger.info("Profile pick: %s", pick)
    return pick

def _zipf_sampler(n_keys: int, skew: float, rng: random.Random) -> Callable[[], int]:
    if n_keys <= 0: raise ValueError("n_keys must be > 0")
    if skew <= 0.0: return lambda: rng.randrange(n_keys)
    weights = [1.0 / ((k + 1) ** skew) for k in range(n_keys)]
    total = sum(weights)
    cdf: List[float] = []
    acc = 0.0
    for w in weights:
        acc += w / total
        cdf.append(acc)
    def sample() -> int:
        x = rng.random()
        lo, hi = 0, n_keys - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if x <= cdf[mid]: hi = mid
            else: lo = mid + 1
        return lo
    return sample

def _adversarialize_key(base_idx: int, lowbits: int) -> int:
    if lowbits <= 0: return base_idx
    mask = (1 << lowbits) - 1
    return (base_idx & ~mask)

def generate_csv(out_path: str, ops: int, read_ratio: float, key_skew: float,
                 key_space: int, seed: int, del_ratio_within_writes: float = 0.2,
                 adversarial_ratio: float = 0.0, adversarial_lowbits: int = 6) -> None:
    if ops <= 0: raise ValueError("ops must be > 0")
    if not (0.0 <= read_ratio <= 1.0): raise ValueError("read_ratio must be in [0,1]")
    if key_space <= 0: raise ValueError("key_space must be > 0")
    if not (0.0 <= del_ratio_within_writes < 1.0): raise ValueError("del_ratio_within_writes in [0,1)")
    if not (0.0 <= adversarial_ratio <= 1.0): raise ValueError("adversarial_ratio in [0,1]")
    rng = random.Random(seed)
    sample_key_idx = _zipf_sampler(key_space, key_skew, rng)
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["op", "key", "value"])
        for _ in range(ops):
            idx = sample_key_idx()
            if rng.random() < adversarial_ratio:
                idx = _adversarialize_key(idx, adversarial_lowbits)
            key = f"K{idx}"
            if rng.random() < read_ratio:
                w.writerow(["get", key, ""])
            else:
                if rng.random() < del_ratio_within_writes:
                    w.writerow(["del", key, ""])
                else:
                    w.writerow(["put", key, str(rng.randint(0, 1_000_000))])

# --------------------------------------------------------------------
# Runner with proactive compaction, JSON summary (+ percentiles), snapshots
# --------------------------------------------------------------------
def run_csv(path: str, mode: str, metrics_port: Optional[int] = None,
            snapshot_in: Optional[str] = None, snapshot_out: Optional[str] = None,
            compress_out: bool = False, compact_interval: Optional[float] = None,
            json_summary_out: Optional[str] = None,
            latency_sample_k: int = 1000, latency_sample_every: int = 128) -> None:
    """
    Replay operations from a CSV workload. Exposes live metrics and writes
    machine-readable summaries for CI pipelines.

    Percentile latency is estimated by sampling every Nth operation (N=latency_sample_every),
    feeding per-op elapsed time (ms) into fixed-size reservoirs (K=latency_sample_k).
    """
    metrics = Metrics()
    server = start_metrics_server(metrics, metrics_port) if metrics_port is not None else None
    # Build or load map
    if snapshot_in:
        with _open_for_read(snapshot_in) as f:
            snap = pickle.load(f)
        if isinstance(snap, (TwoLevelChainingMap, RobinHoodMap, HybridAdaptiveHashMap)):
            m = snap
        elif isinstance(snap, dict) and "backend" in snap:
            m = HybridAdaptiveHashMap.load(snapshot_in)
        else:
            raise TypeError("Unsupported snapshot format")
        logger.info("Loaded snapshot from %s (type=%s)", snapshot_in, type(m).__name__)
    else:
        m = build_map(mode, metrics=metrics)

    _reattach_runtime_callbacks(m, metrics)

    # Per-op latency reservoirs
    want_latency = json_summary_out is not None and latency_sample_k > 0 and latency_sample_every > 0
    overall_res = Reservoir(k=latency_sample_k)
    res_by_op: Dict[str, Reservoir] = {
        "put": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF01),
        "get": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF02),
        "del": Reservoir(k=max(1, latency_sample_k // 3), seed=0xC0FF03),
    }

    def load_ops():
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                yield row["op"], row["key"], row.get("value") or None

    start = time.perf_counter()
    last_compact = start

    try:
        for op_idx, (op, k, v) in enumerate(load_ops(), 1):
            if want_latency and (op_idx % latency_sample_every == 0):
                t0 = time.perf_counter()
                out = run_op(m, op, k, v, metrics=metrics)
                _ = out
                dt_ms = (time.perf_counter() - t0) * 1000.0
                overall_res.offer(dt_ms)
                if op in res_by_op:
                    res_by_op[op].offer(dt_ms)
            else:
                out = run_op(m, op, k, v, metrics=metrics)
                _ = out

            metrics.ops_total += 1
            if metrics.ops_total % 1024 == 0:
                sample_metrics(m, metrics)

            # Proactive compaction
            if compact_interval is not None:
                now = time.perf_counter()
                if now - last_compact >= compact_interval:
                    last_compact = now
                    if isinstance(m, HybridAdaptiveHashMap):
                        if m._migrating_to is None and isinstance(m._backend, RobinHoodMap):
                            logger.info("Proactive compaction tick (interval=%.2fs)", compact_interval)
                            m._backend.compact()
                            metrics.compactions_total += 1
                    elif isinstance(m, RobinHoodMap):
                        logger.info("Proactive compaction tick (interval=%.2fs)", compact_interval)
                        m.compact()
                        metrics.compactions_total += 1

        sample_metrics(m, metrics)
        elapsed = time.perf_counter() - start
        logger.info("run-csv finished in %.6f s, backend=%s", elapsed, metrics.backend_name)

        # JSON summary for CI/CD
        if json_summary_out:
            pct_overall = overall_res.percentiles([0.50, 0.90, 0.99])
            pct_put = res_by_op["put"].percentiles([0.50, 0.90, 0.99])
            pct_get = res_by_op["get"].percentiles([0.50, 0.90, 0.99])
            pct_del = res_by_op["del"].percentiles([0.50, 0.90, 0.99])
            summary = {
                "elapsed_seconds": elapsed,
                "total_ops": metrics.ops_total,
                "ops_per_second": (metrics.ops_total / elapsed) if elapsed > 0 else None,
                "final_backend": metrics.backend_name,
                "migrations_triggered": metrics.migrations_total,
                "compactions_triggered": metrics.compactions_total,
                "latency_ms": {
                    "overall": pct_overall,
                    "put": pct_put,
                    "get": pct_get,
                    "del": pct_del,
                },
                "latency_sample": {
                    "reservoir_k_overall": overall_res.k,
                    "reservoir_k_each": res_by_op["put"].k,
                    "seen_overall": overall_res.n,
                    "every_n_ops": latency_sample_every
                }
            }
            with open(json_summary_out, "w") as jf:
                json.dump(summary, jf, indent=2)
            logger.info("Wrote JSON summary: %s", json_summary_out)

        # Snapshot out
        if snapshot_out:
            if isinstance(m, HybridAdaptiveHashMap):
                m.save(snapshot_out, compress=compress_out)
            elif isinstance(m, (TwoLevelChainingMap, RobinHoodMap)):
                m.save(snapshot_out, compress=compress_out)
            else:
                with _open_for_write(snapshot_out, compress_out) as f:
                    pickle.dump(m, f)
            logger.info("Wrote snapshot to %s (compress=%s)", snapshot_out, compress_out)

    finally:
        if server is not None:
            try:
                server.shutdown()
            finally:
                server.server_close()

# --------------------------------------------------------------------
# Verification (with optional repair)
# --------------------------------------------------------------------
def _verify_chaining(m: TwoLevelChainingMap, verbose: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    total = 0
    for groups in m._buckets:
        for grp in groups:
            total += len(grp)
    ok = (total == m._size)
    if not ok:
        msgs.append(f"Size mismatch: size={m._size}, summed={total}")
    if verbose:
        msgs.append(f"Buckets={m.M}, Groups/Bucket={m.G}, Size={m._size}, MaxGroupLen={m.max_group_len()}")
    return ok, msgs

def _verify_robinhood(m: RobinHoodMap, verbose: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    bound_ok = (m._size + m._tombstones) <= m._cap
    if not bound_ok:
        msgs.append(f"Bound violated: size+tombstones={m._size + m._tombstones} > cap={m._cap}")
    count = sum(1 for _ in m.items())
    size_ok = (count == m._size)
    if not size_ok:
        msgs.append(f"Item iteration count={count} != size={m._size}")
    if verbose:
        msgs.append(f"Cap={m._cap}, Size={m._size}, Tombstones={m._tombstones}, "
                    f"LF={m.load_factor():.3f}, TZ={m.tombstone_ratio():.3f}")
    return (bound_ok and size_ok), msgs

def _verify_hybrid(m: HybridAdaptiveHashMap, verbose: bool) -> Tuple[bool, List[str]]:
    msgs: List[str] = []
    while m._migrating_to:
        m._drain_migration()
    ok = True
    inner = getattr(m, "_backend", None)
    if isinstance(inner, TwoLevelChainingMap):
        ok2, msg2 = _verify_chaining(inner, verbose); ok = ok and ok2; msgs += [f"[backend=chaining] {s}" for s in msg2]
    elif isinstance(inner, RobinHoodMap):
        ok2, msg2 = _verify_robinhood(inner, verbose); ok = ok and ok2; msgs += [f"[backend=robinhood] {s}" for s in msg2]
    else:
        ok = False; msgs.append("Unknown inner backend type")
    if verbose:
        msgs.append(f"Hybrid name={m.backend_name()}, size={len(m)}")
    return ok, msgs

def verify_snapshot(path: str, verbose: bool = False,
                    repair: bool = False, repair_out: Optional[str] = None) -> int:
    """
    Verify invariants of a snapshot. If --repair is passed and the map is a RobinHoodMap
    (or Hybrid with RH active), compacts to purge tombstones / fix counters and writes
    to --out if provided (else in-place rewrite).
    """
    try:
        with _open_for_read(path) as f:
            snap = pickle.load(f)
    except Exception as e:
        print(f"ERROR: failed to load snapshot: {e}")
        return 1

    def write_snapshot(obj: Any, out_path: str) -> None:
        with _open_for_write(out_path, compress=out_path.endswith(".gz")) as wf:
            pickle.dump(obj, wf)

    ok = False
    messages: List[str] = []

    # Dispatch verify
    if isinstance(snap, TwoLevelChainingMap):
        ok, messages = _verify_chaining(snap, verbose)
        target_for_repair = None
    elif isinstance(snap, RobinHoodMap):
        ok, messages = _verify_robinhood(snap, verbose)
        target_for_repair = snap
    elif isinstance(snap, HybridAdaptiveHashMap):
        ok, messages = _verify_hybrid(snap, verbose)
        target_for_repair = None
        inner = getattr(snap, "_backend", None)
        if isinstance(inner, RobinHoodMap):
            target_for_repair = inner
    elif isinstance(snap, dict) and "backend" in snap:
        try:
            m = HybridAdaptiveHashMap.load(path)
            ok, messages = _verify_hybrid(m, verbose)
            inner = getattr(m, "_backend", None)
            target_for_repair = inner if isinstance(inner, RobinHoodMap) else None
            snap = m
        except Exception as e:
            print(f"ERROR: invalid hybrid state: {e}")
            return 1
    else:
        print("ERROR: unsupported snapshot object")
        return 1

    # Report
    if ok:
        print("OK: snapshot verified")
    else:
        print("FAIL: snapshot invariants violated")
    for msg in messages:
        print(msg)

    # Optional repair (safe compaction only)
    if repair and target_for_repair is not None:
        print("Attempting safe repair (compaction of RobinHoodMap)...")
        try:
            target_for_repair.compact()
            out_path = repair_out or path
            if isinstance(snap, (TwoLevelChainingMap, RobinHoodMap)):
                write_snapshot(snap, out_path)
            else:
                snap.save(out_path, compress=out_path.endswith(".gz"))
            print(f"Repair complete. Wrote repaired snapshot to: {out_path}")
            # Post-repair check
            if isinstance(snap, TwoLevelChainingMap):
                ok2, _ = _verify_chaining(snap, False)
            elif isinstance(snap, RobinHoodMap):
                ok2, _ = _verify_robinhood(snap, False)
            else:
                ok2, _ = _verify_hybrid(snap, False)
            print("Post-repair verification:", "OK" if ok2 else "FAILED")
            ok = ok and ok2
        except Exception as e:
            print(f"ERROR: repair failed: {e}")
            return 1
    elif repair and target_for_repair is None:
        print("NOTICE: --repair requested but snapshot/backend is not a RobinHoodMap; no safe repair applicable.")

    return 0 if ok else 1

# --------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------
def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="HashMap CLI with multi-backend, adaptive mode, generator, profiler, metrics, snapshots, verification (with repair), and CI summaries.")
    p.add_argument("--mode", default="adaptive",
                   choices=["fast-insert", "fast-lookup", "memory-tight", "adaptive"],
                   help="Select backend when not loading a snapshot.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Simple ops
    p_put = sub.add_parser("put");  p_put.add_argument("key"); p_put.add_argument("value")
    p_get = sub.add_parser("get");  p_get.add_argument("key")
    p_del = sub.add_parser("del");  p_del.add_argument("key")
    sub.add_parser("items")

    # Profile
    p_prof = sub.add_parser("profile", help="Profile a CSV workload and print the recommended mode.")
    p_prof.add_argument("--csv", required=True)
    p_prof.add_argument("--then", nargs=argparse.REMAINDER, help="After profiling, run one command with the picked mode.")

    # Generator
    p_gen = sub.add_parser("generate-csv", help="Generate a synthetic workload CSV.")
    p_gen.add_argument("--outfile", required=True)
    p_gen.add_argument("--ops", type=int, default=100000)
    p_gen.add_argument("--read-ratio", type=float, default=0.8)
    p_gen.add_argument("--key-skew", type=float, default=0.0)
    p_gen.add_argument("--key-space", type=int, default=10000)
    p_gen.add_argument("--seed", type=int, default=1337)
    p_gen.add_argument("--del-ratio", type=float, default=0.2)
    p_gen.add_argument("--adversarial-ratio", type=float, default=0.0)
    p_gen.add_argument("--adversarial-lowbits", type=int, default=6)

    # Runner
    p_run = sub.add_parser("run-csv", help="Replay a CSV workload (metrics, snapshots, compaction, JSON summary).")
    p_run.add_argument("--csv", required=True)
    p_run.add_argument("--metrics-port", type=int, default=None)
    p_run.add_argument("--snapshot-in", type=str, default=None, help="Load initial snapshot (.gz auto-detected)")
    p_run.add_argument("--snapshot-out", type=str, default=None, help="Write snapshot after run")
    p_run.add_argument("--compress", action="store_true", help="Gzip-compress snapshot writes or use .gz suffix")
    p_run.add_argument("--compact-interval", type=float, default=None, help="Seconds between proactive compactions")
    p_run.add_argument("--json-summary-out", type=str, default=None, help="Write final run stats to JSON for CI")
    p_run.add_argument("--latency-sample-k", type=int, default=1000, help="Reservoir size for latency sampling")
    p_run.add_argument("--latency-sample-every", type=int, default=128, help="Sample every Nth operation")

    # Offline compaction
    p_comp = sub.add_parser("compact-snapshot", help="Compact a RobinHoodMap snapshot offline.")
    p_comp.add_argument("--in", dest="infile", required=True)
    p_comp.add_argument("--out", dest="outfile", required=True)
    p_comp.add_argument("--compress", action="store_true")

    # Verification
    p_ver = sub.add_parser("verify-snapshot", help="Verify invariants of a snapshot; optional safe repair (RobinHoodMap).")
    p_ver.add_argument("--in", dest="infile", required=True)
    p_ver.add_argument("--verbose", action="store_true")
    p_ver.add_argument("--repair", action="store_true", help="Attempt safe repair (RobinHood compaction).")
    p_ver.add_argument("--out", dest="outfile", default=None, help="Write repaired snapshot to this path (default: overwrite input)")

    args = p.parse_args(argv)

    # One-shot ops
    if args.cmd in ("put", "get", "del", "items"):
        m = build_map(args.mode)
        out = run_op(m, args.cmd, getattr(args, "key", None), getattr(args, "value", None))
        if out is not None:
            print(out)
        return 0

    if args.cmd == "profile":
        pick = profile_csv(args.csv)
        print(pick)
        if args.then:
            return main(["--mode", pick] + args.then)
        return 0

    if args.cmd == "generate-csv":
        generate_csv(args.outfile, args.ops, args.read_ratio, args.key_skew,
                     args.key_space, args.seed, del_ratio_within_writes=args.del_ratio,
                     adversarial_ratio=args.adversarial_ratio, adversarial_lowbits=args.adversarial_lowbits)
        logger.info("Wrote workload CSV: %s", args.outfile)
        return 0

    if args.cmd == "run-csv":
        run_csv(args.csv, args.mode, metrics_port=args.metrics_port,
                snapshot_in=args.snapshot_in, snapshot_out=args.snapshot_out,
                compress_out=args.compress, compact_interval=args.compact_interval,
                json_summary_out=args.json_summary_out,
                latency_sample_k=args.latency_sample_k, latency_sample_every=args.latency_sample_every)
        return 0

    if args.cmd == "compact-snapshot":
        rh = RobinHoodMap.load(args.infile)
        logger.info("Loaded RobinHoodMap snapshot cap=%d size=%d tombstones≈%.2f%%",
                    rh._cap, len(rh), rh.tombstone_ratio()*100.0)
        rh.compact()
        rh.save(args.outfile, compress=args.compress)
        logger.info("Wrote compacted snapshot: %s cap=%d size=%d tombstones≈%.2f%%",
                    args.outfile, rh._cap, len(rh), rh.tombstone_ratio()*100.0)
        return 0

    if args.cmd == "verify-snapshot":
        return verify_snapshot(args.infile, verbose=args.verbose,
                               repair=args.repair, repair_out=args.outfile)

    return 1

if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(2)
