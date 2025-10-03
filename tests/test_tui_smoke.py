from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock, patch

from adhash.tui.app import _format_history, _format_summary, fetch_history, fetch_metrics


class DummyResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def test_fetch_metrics_returns_none_on_bad_payload() -> None:
    with patch("adhash.tui.app.urlopen", MagicMock(return_value=DummyResponse(b"not json"))):
        assert fetch_metrics("http://example.com") is None


def test_fetch_history_returns_none_on_bad_payload() -> None:
    with patch("adhash.tui.app.urlopen", MagicMock(return_value=DummyResponse(b"oops"))):
        assert fetch_history("http://example.com") is None


def test_format_summary_handles_partial_tick() -> None:
    tick: Dict[str, Any] = {
        "backend": "chaining",
        "ops": 128,
        "ops_by_type": {"put": 64, "get": 60, "del": 4},
        "load_factor": 0.42,
        "avg_probe_estimate": 1.0,
        "max_group_len": 2.0,
        "migrations": 1,
        "compactions": 0,
        "latency_ms": {"overall": {"p50": 0.5, "p90": 0.8, "p99": 1.2}},
    }

    summary = _format_summary(tick)
    assert "Backend: chaining" in summary
    assert "Ops: 128" in summary


def test_format_history_reports_trends() -> None:
    history = [
        {"t": 0.0, "ops": 0, "load_factor": 0.10, "migrations": 0},
        {"t": 1.0, "ops": 100, "load_factor": 0.20, "migrations": 0},
        {"t": 2.0, "ops": 240, "load_factor": 0.25, "migrations": 1},
    ]
    text = _format_history(history)
    assert "Load factor trend" in text
    assert "Migrations so far: 1" in text
