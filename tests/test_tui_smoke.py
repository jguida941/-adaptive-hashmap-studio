from __future__ import annotations

import asyncio
import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from adhash.tui import app as tui_app
from adhash.tui.app import (
    SUMMARY_SCHEMA,
    AdaptiveMetricsApp,
    _TEXTUAL_ERR,
    _build_headers,
    _format_alerts,
    _format_history,
    _format_summary,
    fetch_history,
    fetch_metrics,
)


class DummyResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class DummyWidget:
    def __init__(self) -> None:
        self.value = ""

    def update(self, message: str) -> None:
        self.value = message


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


def test_format_alerts_formats_messages() -> None:
    alerts = [
        {"severity": "warning", "message": "High load"},
        {"severity": "info", "metric": "avg_probe"},
    ]
    output = _format_alerts(alerts)
    assert "🚩 High load" in output
    assert "Guardrail" in output


def test_build_headers_includes_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret-token")
    headers = _build_headers("application/json")
    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == "Bearer secret-token"


def test_fetch_metrics_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"ops": 10}).encode("utf-8")
    monkeypatch.setattr("adhash.tui.app.urlopen", MagicMock(return_value=DummyResponse(payload)))
    data = fetch_metrics("http://localhost/api/metrics")
    assert data == {"ops": 10}


def test_fetch_history_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps([{"ops": 1}]).encode("utf-8")
    monkeypatch.setattr("adhash.tui.app.urlopen", MagicMock(return_value=DummyResponse(payload)))
    data = fetch_history("http://localhost/api/metrics/history")
    assert data == [{"ops": 1}]


def test_poll_and_render_updates_widgets(monkeypatch: pytest.MonkeyPatch) -> None:
    if _TEXTUAL_ERR is not None:
        pytest.skip("Textual not available")

    app = AdaptiveMetricsApp(
        metrics_endpoint="http://127.0.0.1:9090/api/metrics",
        poll_interval=0.1,
    )
    summary = DummyWidget()
    status = DummyWidget()
    history = DummyWidget()
    alerts = DummyWidget()
    setattr(app, "_summary", summary)
    setattr(app, "_status", status)
    setattr(app, "_history", history)
    setattr(app, "_alerts", alerts)

    monkeypatch.setattr(
        tui_app,
        "fetch_metrics",
        lambda endpoint, timeout: {
            "schema": SUMMARY_SCHEMA,
            "backend": "adaptive",
            "ops": 1,
            "ops_by_type": {"put": 1},
            "alerts": [],
        },
    )
    monkeypatch.setattr(
        tui_app,
        "fetch_history",
        lambda endpoint, timeout: [
            {"t": 0.0, "ops": 0, "load_factor": 0.1},
            {"t": 1.0, "ops": 1, "load_factor": 0.2},
        ],
    )

    async def runner() -> None:
        await app._poll_and_render(initial=True)

    asyncio.run(runner())
    assert "Backend: adaptive" in summary.value
    assert "Last update" in status.value
    assert "Load factor trend" in history.value
    assert alerts.value == "No active alerts."


def test_poll_and_render_handles_missing_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    if _TEXTUAL_ERR is not None:
        pytest.skip("Textual not available")

    app = AdaptiveMetricsApp(metrics_endpoint="http://127.0.0.1:9090/api/metrics")
    summary = DummyWidget()
    status = DummyWidget()
    history = DummyWidget()
    alerts = DummyWidget()
    setattr(app, "_summary", summary)
    setattr(app, "_status", status)
    setattr(app, "_history", history)
    setattr(app, "_alerts", alerts)

    monkeypatch.setattr(tui_app, "fetch_metrics", lambda endpoint, timeout: None)
    asyncio.run(app._poll_and_render(initial=True))
    assert "Waiting for metrics" in summary.value
    assert "Waiting for metrics" in status.value


def test_fetch_tick_and_history_rejects_unknown_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    if _TEXTUAL_ERR is not None:
        pytest.skip("Textual not available")

    app = AdaptiveMetricsApp(metrics_endpoint="http://127.0.0.1:9090/api/metrics")
    monkeypatch.setattr(tui_app, "fetch_metrics", lambda endpoint, timeout: {"schema": "mystery"})
    tick, history, error = asyncio.run(app._fetch_tick_and_history())
    assert tick is None
    assert history is None
    assert error == "Unsupported schema: mystery"
