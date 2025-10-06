from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from adhash.tui import app as tui_app

AdaptiveMetricsApp = tui_app.AdaptiveMetricsApp


if getattr(tui_app, "_TEXTUAL_ERR", None) is not None:  # pragma: no cover - textual optional
    pytestmark = pytest.mark.skip(reason="Textual not available")


def make_trace() -> dict[str, Any]:
    return {
        "backend": "robinhood",
        "operation": "get",
        "key_repr": "'K1'",
        "found": True,
        "terminal": "match",
        "path": [
            {"step": 0, "slot": 3, "state": "occupied", "matches": True},
        ],
    }


def test_load_probe_trace_reads_file(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps({"trace": make_trace()}), encoding="utf-8")

    app = AdaptiveMetricsApp(
        metrics_endpoint="http://127.0.0.1:9090/api/metrics",
        probe_trace=str(trace_path),
    )

    message = app._load_probe_trace()

    assert "Probe visualization" in message
    assert str(trace_path) in message


def test_reload_probe_updates_panel(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps({"trace": make_trace()}), encoding="utf-8")

    app = AdaptiveMetricsApp(
        metrics_endpoint="http://127.0.0.1:9090/api/metrics",
        probe_trace=str(trace_path),
    )

    class DummyProbe:
        def __init__(self) -> None:
            self.value = ""

        def update(self, message: str) -> None:
            self.value = message

    dummy_probe = DummyProbe()
    cast(Any, app)._probe = dummy_probe

    asyncio.run(app.action_reload_probe())
    assert "Probe visualization" in dummy_probe.value


def test_reload_probe_without_path_sets_hint() -> None:
    app = AdaptiveMetricsApp(
        metrics_endpoint="http://127.0.0.1:9090/api/metrics",
    )

    class DummyStatus:
        def __init__(self) -> None:
            self.value = ""

        def update(self, message: str) -> None:
            self.value = message

    dummy_status = DummyStatus()
    cast(Any, app)._status = dummy_status

    asyncio.run(app.action_reload_probe())

    assert "--probe-json" in dummy_status.value
