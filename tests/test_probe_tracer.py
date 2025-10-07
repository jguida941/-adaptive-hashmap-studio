from __future__ import annotations

from adhash.analysis.probe import (
    _json_friendly,
    format_trace_lines,
    trace_probe_get,
    trace_probe_put,
)
from adhash.core.maps import HybridAdaptiveHashMap, RobinHoodMap, TwoLevelChainingMap


def test_trace_robinhood_get_found() -> None:
    m = RobinHoodMap(initial_capacity=8)
    m.put("A", 1)
    m.put("B", 2)
    trace = trace_probe_get(m, "A")
    assert trace["backend"] == "robinhood"
    assert trace["found"] is True
    path = trace["path"]
    assert any(step.get("matches") for step in path)


def test_trace_robinhood_get_absent() -> None:
    m = RobinHoodMap(initial_capacity=4)
    m.put("A", 1)
    trace = trace_probe_get(m, "missing")
    assert trace["found"] is False
    assert trace["terminal"] in {"empty", "tombstone"}


def test_trace_robinhood_get_handles_tombstone() -> None:
    m = RobinHoodMap(initial_capacity=4)
    m.put("A", 1)
    m.put("B", 2)
    assert m.delete("A") is True

    trace = trace_probe_get(m, "A")
    states = [step.get("state") for step in trace["path"]]
    assert "tombstone" in states
    assert trace["found"] is False


def test_trace_robinhood_put_reports_swap() -> None:
    m = RobinHoodMap(initial_capacity=4)
    # Craft a collision scenario
    m.put("A", 1)
    m.put("B", 2)
    trace = trace_probe_put(m, "C", 3)
    assert trace["operation"] == "put"
    assert any("action" in step for step in trace["path"])


def test_trace_robinhood_put_updates_existing_key() -> None:
    m = RobinHoodMap(initial_capacity=4)
    m.put("A", 1)
    trace = trace_probe_put(m, "A", 5)
    assert trace["terminal"] == "update"
    assert any(step.get("action") == "update" for step in trace["path"])


def test_trace_robinhood_put_reuses_tombstone() -> None:
    m = RobinHoodMap(initial_capacity=4)
    m.put("A", 1)
    assert m.delete("A") is True
    trace = trace_probe_put(m, "A", 2)
    assert trace["terminal"] == "reuse-tombstone"
    assert any(step.get("state") == "tombstone" for step in trace["path"])


def test_trace_robinhood_put_accounts_for_resize() -> None:
    m = RobinHoodMap(initial_capacity=8)
    for i in range(7):
        m.put(f"key-{i}", i)

    trace = trace_probe_put(m, "new-key", 99)

    assert trace.get("capacity") == 16
    assert trace.get("resized") is True
    slots = [step["slot"] for step in trace["path"] if isinstance(step, dict) and "slot" in step]
    assert all(0 <= slot < 16 for slot in slots)


def test_trace_chaining_get_group() -> None:
    m = TwoLevelChainingMap(initial_buckets=4, groups_per_bucket=4)
    m.put("A", 1)
    trace = trace_probe_get(m, "A")
    assert trace["backend"] == "chaining"
    assert trace["found"] is True
    assert trace["group_size"] >= 1


def test_trace_hybrid_delegates_backend() -> None:
    m = HybridAdaptiveHashMap()
    m.put("alpha", 1)
    trace = trace_probe_get(m, "alpha")
    assert "adaptive_backend" in trace
    assert trace["found"] is True


def test_format_trace_lines_includes_steps() -> None:
    trace = {
        "backend": "robinhood",
        "operation": "get",
        "key_repr": "'K1'",
        "found": True,
        "terminal": "match",
        "capacity": 8,
        "path": [
            {"step": 0, "slot": 3, "state": "occupied", "matches": True},
        ],
    }
    lines = format_trace_lines(trace, snapshot="foo", seeds=["A=1"], export_path="trace.json")
    joined = "\n".join(lines)
    assert "Probe visualization" in joined
    assert "Snapshot: foo" in joined
    assert "Seed entries" in joined
    assert "trace.json" in joined


def test_json_friendly_falls_back_to_repr() -> None:
    class NonSerializable:
        def __repr__(self) -> str:
            return "<non-serialisable>"

    value = NonSerializable()
    assert _json_friendly(value) == "<non-serialisable>"
