from __future__ import annotations

import json
import time
import urllib.request
from collections import deque

import pytest

from adhash.metrics.constants import SUMMARY_SCHEMA, TICK_SCHEMA
from adhash.metrics.core import Metrics, apply_tick_to_metrics
from adhash.metrics.server import start_metrics_server


@pytest.mark.parametrize("path", ["/api/metrics", "/api/metrics/history?limit=1"])
def test_metrics_server_serves_json(path: str) -> None:
    metrics = Metrics()
    metrics.history_buffer = deque(maxlen=16)
    try:
        server, stop = start_metrics_server(metrics, port=0, host="127.0.0.1")
    except PermissionError as exc:  # pragma: no cover - environment restriction
        pytest.skip(f"socket bind not permitted: {exc}")
    try:
        tick = {
            "schema": TICK_SCHEMA,
            "generated_at": time.time(),
            "ops": 42,
            "ops_by_type": {"put": 10, "get": 32, "del": 0},
            "migrations": 1,
            "compactions": 0,
            "load_factor": 0.55,
            "max_group_len": 3,
            "avg_probe_estimate": 1.2,
            "tombstone_ratio": 0.01,
            "backend": "adaptive",
        }
        apply_tick_to_metrics(metrics, tick)
        port = server.server_port
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert "schema" in payload
        if path.endswith("summary.json"):
            assert payload["schema"] == SUMMARY_SCHEMA
            assert payload["totals"]["ops"] == 42
        else:
            assert payload["schema"]
            assert payload["items"], "history response should include items"
    finally:
        stop()
