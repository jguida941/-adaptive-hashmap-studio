"""Probe-path tracing utilities for Adaptive Hash Map variants."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from adhash.core.maps import (
    HybridAdaptiveHashMap,
    RobinHoodMap,
    TwoLevelChainingMap,
    _RHEntry,
    _TOMBSTONE,
)

ProbeTrace = Dict[str, Any]


def _json_friendly(value: Any) -> Any:
    """Return a JSON-serialisable representation of ``value``."""

    try:
        import json

        json.dumps(value)
        return value
    except Exception:  # noqa: BLE001
        return repr(value)


def trace_robinhood_get(map_obj: RobinHoodMap, key: Any) -> ProbeTrace:
    mask = map_obj._mask  # pylint: disable=protected-access
    cap = map_obj._cap  # pylint: disable=protected-access
    start_idx = map_obj._idx(hash(key))  # pylint: disable=protected-access
    idx = start_idx
    scanned = 0
    path: List[Dict[str, Any]] = []
    found = False
    terminal = "overflow"
    while scanned <= cap:
        slot = map_obj._table[idx]  # pylint: disable=protected-access
        step: Dict[str, Any] = {
            "step": scanned,
            "slot": idx,
            "start_slot": start_idx,
        }
        if slot is None:
            step.update({"state": "empty"})
            path.append(step)
            terminal = "empty"
            break
        if slot is _TOMBSTONE:
            step.update({"state": "tombstone"})
            path.append(step)
            idx = (idx + 1) & mask
            scanned += 1
            continue
        if isinstance(slot, _RHEntry):
            ideal = map_obj._idx(hash(slot.key))  # pylint: disable=protected-access
            distance = map_obj._probe_distance(ideal, idx)  # pylint: disable=protected-access
            matches = slot.key == key
            step.update(
                {
                    "state": "occupied",
                    "key_repr": repr(slot.key),
                    "value_repr": repr(slot.value),
                    "ideal_slot": ideal,
                    "probe_distance": distance,
                    "matches": matches,
                }
            )
            path.append(step)
            if matches:
                terminal = "match"
                found = True
                break
        idx = (idx + 1) & mask
        scanned += 1
    return {
        "backend": "robinhood",
        "operation": "get",
        "key_repr": repr(key),
        "found": found,
        "terminal": terminal,
        "capacity": cap,
        "path": path,
    }


def _probe_distance_for_cap(capacity: int, ideal_idx: int, cur_idx: int) -> int:
    """Compute a wrap-aware probe distance for the given capacity."""

    return cur_idx - ideal_idx if cur_idx >= ideal_idx else (cur_idx + capacity) - ideal_idx


def _rehash_robinhood_table(
    map_obj: RobinHoodMap,
) -> tuple[int, int, List[Optional[Any]], bool]:
    """Return a simulated table (capacity/mask/table) mirroring resize behaviour."""

    needs_resize = map_obj.load_factor() > 0.85
    if needs_resize:
        cap = map_obj._cap * 2  # pylint: disable=protected-access
        mask = cap - 1
        table: List[Optional[Any]] = [None] * cap
        for slot in map_obj._table:  # pylint: disable=protected-access
            if isinstance(slot, _RHEntry):
                idx = hash(slot.key) & mask
                current = slot
                dist = 0
                while True:
                    occupant = table[idx]
                    if occupant is None or occupant is _TOMBSTONE:
                        table[idx] = current
                        break
                    if isinstance(occupant, _RHEntry) and occupant.key == slot.key:
                        table[idx] = current
                        break
                    if not isinstance(occupant, _RHEntry):
                        table[idx] = current
                        break
                    ideal = hash(occupant.key) & mask
                    slot_dist = _probe_distance_for_cap(cap, ideal, idx)
                    if slot_dist < dist:
                        table[idx], current = current, occupant
                        dist = slot_dist
                    idx = (idx + 1) & mask
                    dist += 1
        return cap, mask, table, True
    cap = map_obj._cap  # pylint: disable=protected-access
    mask = map_obj._mask  # pylint: disable=protected-access
    table = list(map_obj._table)  # pylint: disable=protected-access
    return cap, mask, table, False


def trace_robinhood_put(map_obj: RobinHoodMap, key: Any, value: Any) -> ProbeTrace:
    cap, mask, table, resized = _rehash_robinhood_table(map_obj)
    idx = hash(key) & mask
    current = _RHEntry(key, value)
    dist = 0
    path: List[Dict[str, Any]] = []
    steps = 0
    terminal = "insert"
    while steps <= cap + 1:
        slot = table[idx]
        step: Dict[str, Any] = {
            "step": steps,
            "slot": idx,
            "candidate_key": repr(current.key),
        }
        if slot is None:
            step.update({"state": "empty", "action": "insert"})
            path.append(step)
            terminal = "insert"
            break
        if slot is _TOMBSTONE:
            step.update({"state": "tombstone", "action": "fill"})
            path.append(step)
            terminal = "reuse-tombstone"
            break
        if isinstance(slot, _RHEntry):
            ideal = hash(slot.key) & mask
            slot_dist = _probe_distance_for_cap(cap, ideal, idx)
            matches = slot.key == key
            step.update(
                {
                    "state": "occupied",
                    "occupant_key": repr(slot.key),
                    "occupant_value": repr(slot.value),
                    "ideal_slot": ideal,
                    "probe_distance": slot_dist,
                    "matches": matches,
                }
            )
            if matches:
                step["action"] = "update"
                path.append(step)
                terminal = "update"
                break
            if slot_dist < dist:
                step["action"] = "swap"
                step["swap_with"] = repr(current.key)
                table[idx], current = current, slot
                dist = slot_dist
            else:
                step["action"] = "advance"
            path.append(step)
        else:
            step.update({"state": repr(slot), "action": "advance"})
            path.append(step)
        idx = (idx + 1) & mask
        dist += 1
        steps += 1
    else:
        terminal = "overflow"
    return {
        "backend": "robinhood",
        "operation": "put",
        "key_repr": repr(key),
        "value_repr": _json_friendly(value),
        "terminal": terminal,
        "capacity": cap,
        "resized": resized,
        "path": path,
    }


def trace_chaining_get(map_obj: TwoLevelChainingMap, key: Any) -> ProbeTrace:
    bucket_idx, group_idx = map_obj._index_group(key)  # pylint: disable=protected-access
    group = map_obj._buckets[bucket_idx][group_idx]  # pylint: disable=protected-access
    entries: List[Dict[str, Any]] = []
    found = False
    for pos, entry in enumerate(group):
        matches = entry.key == key
        entries.append(
            {
                "position": pos,
                "key_repr": repr(entry.key),
                "value_repr": repr(entry.value),
                "matches": matches,
            }
        )
        if matches:
            found = True
    return {
        "backend": "chaining",
        "operation": "get",
        "key_repr": repr(key),
        "bucket": bucket_idx,
        "group": group_idx,
        "group_size": len(group),
        "found": found,
        "path": entries,
    }


def trace_probe_get(
    map_obj: Union[RobinHoodMap, TwoLevelChainingMap, HybridAdaptiveHashMap], key: Any
) -> ProbeTrace:
    if isinstance(map_obj, RobinHoodMap):
        return trace_robinhood_get(map_obj, key)
    if isinstance(map_obj, TwoLevelChainingMap):
        return trace_chaining_get(map_obj, key)
    if isinstance(map_obj, HybridAdaptiveHashMap):
        backend = map_obj.backend()
        trace = trace_probe_get(backend, key)
        trace["adaptive_backend"] = map_obj.backend_name()
        return trace
    raise TypeError(f"Unsupported map type: {type(map_obj)!r}")


def trace_probe_put(
    map_obj: Union[RobinHoodMap, TwoLevelChainingMap, HybridAdaptiveHashMap], key: Any, value: Any
) -> ProbeTrace:
    if isinstance(map_obj, RobinHoodMap):
        return trace_robinhood_put(map_obj, key, value)
    if isinstance(map_obj, TwoLevelChainingMap):
        base = trace_chaining_get(map_obj, key)
        base.update(
            {
                "operation": "put",
                "value_repr": _json_friendly(value),
                "terminal": "update" if base.get("found") else "append",
            }
        )
        return base
    if isinstance(map_obj, HybridAdaptiveHashMap):
        backend = map_obj.backend()
        trace = trace_probe_put(backend, key, value)
        trace["adaptive_backend"] = map_obj.backend_name()
        return trace
    raise TypeError(f"Unsupported map type: {type(map_obj)!r}")


def format_trace_lines(
    trace: Dict[str, Any],
    *,
    snapshot: Optional[Union[str, Path]] = None,
    seeds: Optional[Sequence[str]] = None,
    export_path: Optional[Union[str, Path]] = None,
) -> List[str]:
    """Return a human-friendly rendering of a probe trace."""

    lines: List[str] = []
    backend = trace.get("backend", "?")
    operation = trace.get("operation", "?")
    key_repr = trace.get("key_repr", "?")
    lines.append(f"Probe visualization [{backend}] {operation.upper()} key={key_repr}")
    lines.append(f"Found: {trace.get('found')} | Terminal: {trace.get('terminal')}")
    if backend == "robinhood" and "capacity" in trace:
        capacity_line = f"Capacity: {trace['capacity']}"
        if trace.get("resized"):
            capacity_line += " (after resize)"
        lines.append(capacity_line)
    adaptive_backend = trace.get("adaptive_backend")
    if adaptive_backend:
        lines.append(f"Adaptive backend: {adaptive_backend}")
    if snapshot:
        lines.append(f"Snapshot: {snapshot}")
    if seeds:
        lines.append("Seed entries: " + ", ".join(seeds))
    lines.append("Steps:")
    path = trace.get("path")
    if not isinstance(path, list) or not path:
        lines.append("  (no path recorded)")
    else:
        for item in path:
            if not isinstance(item, dict):
                lines.append(f"  {item!r}")
                continue
            prefix = "  "
            if "step" in item:
                prefix += f"Step {item['step']}: "
            elif "position" in item:
                prefix += f"Entry {item['position']}: "
            else:
                prefix += "Item: "
            attrs: List[str] = []
            for key in (
                "slot",
                "start_slot",
                "position",
                "state",
                "action",
                "ideal_slot",
                "probe_distance",
                "matches",
                "key_repr",
                "occupant_key",
                "candidate_key",
            ):
                if key in item and item[key] is not None:
                    value = item[key]
                    if isinstance(value, bool):
                        value = str(value).lower()
                    attrs.append(f"{key}={value}")
            if not attrs:
                attrs.append(", ".join(f"{k}={v}" for k, v in item.items()))
            lines.append(prefix + ", ".join(attrs))
    if export_path:
        lines.append(f"Trace JSON written to: {export_path}")
    return lines


__all__ = [
    "trace_probe_get",
    "trace_probe_put",
    "trace_robinhood_get",
    "trace_robinhood_put",
    "trace_chaining_get",
    "format_trace_lines",
]
