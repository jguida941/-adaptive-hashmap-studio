from __future__ import annotations

import gzip
import json
import time
from collections import deque
from typing import Any, Dict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from adhash.metrics import (
    KEY_HEATMAP_SCHEMA,
    LATENCY_HISTOGRAM_SCHEMA,
    Metrics,
    PROBE_HISTOGRAM_SCHEMA,
    TICK_SCHEMA,
    start_metrics_server,
)
from hashmap_cli import TwoLevelChainingMap, collect_key_heatmap


def wait_for_server(port: int, retries: int = 10, delay: float = 0.05, headers: Dict[str, str] | None = None) -> None:
    """Helper to wait until the HTTP server starts accepting connections."""

    for _ in range(retries):
        try:
            request = Request(
                f"http://127.0.0.1:{port}/api/metrics",
                headers=headers or {"Accept": "application/json"},
            )
            with urlopen(request, timeout=0.1):
                return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("metrics server did not start in time")


def test_histogram_endpoints_expose_json() -> None:
    metrics_payload: Dict[str, Any] = {
        "schema": TICK_SCHEMA,
        "t": 12.5,
        "latency_hist_ms": {
            "overall": [
                {"le": "0.100000", "count": 3},
                {"le": "+Inf", "count": 5},
            ]
        },
        "probe_hist": [[0, 4], [1, 2]],
        "key_heatmap": {
            "rows": 1,
            "cols": 2,
            "matrix": [[4, 2]],
            "max": 4,
            "total": 6,
            "slot_span": 1,
            "original_slots": 2,
        },
        "latency_hist_preset": "default",
    }
    metrics = Metrics()
    metrics.latest_tick = metrics_payload
    metrics.latency_histograms = {"overall": [(0.1, 3), (float("inf"), 5)]}
    metrics.key_heatmap = metrics_payload["key_heatmap"]

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port, headers={"Authorization": "Bearer secret", "Accept": "application/json"})

        def read_json(path: str) -> Dict[str, Any]:
            with urlopen(path, timeout=0.5) as response:
                payload = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    payload = gzip.decompress(payload)
            return json.loads(payload.decode("utf-8"))

        latency = read_json(f"http://127.0.0.1:{port}/api/metrics/histogram/latency")
        assert latency["schema"] == LATENCY_HISTOGRAM_SCHEMA
        assert latency["operations"]["overall"][0]["count"] == 3
        assert latency.get("preset") == "default"

        probe = read_json(f"http://127.0.0.1:{port}/api/metrics/histogram/probe")
        assert probe["schema"] == PROBE_HISTOGRAM_SCHEMA
        assert probe["buckets"][0] == {"distance": 0, "count": 4}

        heatmap = read_json(f"http://127.0.0.1:{port}/api/metrics/heatmap")
        assert heatmap["schema"] == KEY_HEATMAP_SCHEMA
        assert heatmap["total"] == 6
        assert heatmap["matrix"] == [[4, 2]]
    finally:
        stop_server()


def test_collect_key_heatmap_tracks_counts() -> None:
    table = TwoLevelChainingMap(initial_buckets=4, groups_per_bucket=2)
    for idx in range(6):
        table.put(f"k{idx}", idx)
    heatmap = collect_key_heatmap(table, target_cols=4, max_cells=4)
    assert heatmap["total"] == 6
    assert heatmap["rows"] >= 1
    assert heatmap["matrix"]
    # slot span should be at least one and aggregated cells should sum to total
    flattened = [value for row in heatmap["matrix"] for value in row]
    assert sum(flattened) == 6


def test_history_csv_endpoint_returns_rows() -> None:
    metrics = Metrics()
    metrics.history_buffer = deque(maxlen=4)
    metrics.history_buffer.append(
        {
            "t": 0.0,
            "ops": 0,
            "ops_per_second_ema": 100.0,
            "load_factor": 0.1,
            "avg_probe_estimate": 1.2,
            "tombstone_ratio": 0.0,
            "backend": "chaining",
            "state": "running",
        }
    )
    metrics.latest_tick = metrics.history_buffer[-1]

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(
            port,
            headers={"Authorization": "Bearer secret", "Accept": "application/json"},
        )
        with urlopen(f"http://127.0.0.1:{port}/api/metrics/history.csv?limit=2", timeout=0.5) as response:
            assert response.status == 200
            assert response.headers.get("Content-Type", "").startswith("text/csv")
            body = response.read().decode("utf-8")
        lines = [line for line in body.strip().splitlines() if line]
        assert len(lines) >= 2
        header = lines[0].split(",")
        assert header[:4] == ["t", "ops", "ops_per_second_ema", "ops_per_second_instant"]
        first_row = lines[1].split(",")
        assert first_row[1] == "0"
    finally:
        stop_server()


def test_dashboard_requires_token_and_embeds_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")
    metrics = Metrics()

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)

        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"http://127.0.0.1:{port}/", timeout=0.5)
        assert exc_info.value.code == 401

        with urlopen(f"http://127.0.0.1:{port}/?token=secret", timeout=0.5) as response:
            html_body = response.read().decode("utf-8")
        assert '<meta name="adhash-token" content="secret"/>' in html_body

        request = Request(
            f"http://127.0.0.1:{port}/api/metrics",
            headers={"Authorization": "Bearer secret", "Accept": "application/json"},
        )
        with urlopen(request, timeout=0.5) as response:
            assert response.status == 200
    finally:
        stop_server()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)
