from __future__ import annotations

import json
import time
from typing import Any, Dict
from urllib.request import urlopen

import pytest

import hashmap_cli as cli


def wait_for_server(port: int, retries: int = 10, delay: float = 0.05) -> None:
    """Helper to wait until the HTTP server starts accepting connections."""

    for _ in range(retries):
        try:
            with urlopen(f"http://127.0.0.1:{port}/api/metrics", timeout=0.1):
                return
        except Exception:
            time.sleep(delay)
    raise RuntimeError("metrics server did not start in time")


def test_histogram_endpoints_expose_json() -> None:
    metrics_payload: Dict[str, Any] = {
        "schema": "metrics.v1",
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
    metrics = cli.Metrics()
    metrics.latest_tick = metrics_payload
    metrics.latency_histograms = {"overall": [(0.1, 3), (float("inf"), 5)]}
    metrics.key_heatmap = metrics_payload["key_heatmap"]

    try:
        server = cli.start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)

        latency = json.loads(urlopen(f"http://127.0.0.1:{port}/api/metrics/histogram/latency", timeout=0.5).read())
        assert latency["schema"] == "metrics.latency_histogram.v1"
        assert latency["operations"]["overall"][0]["count"] == 3
        assert latency.get("preset") == "default"

        probe = json.loads(urlopen(f"http://127.0.0.1:{port}/api/metrics/histogram/probe", timeout=0.5).read())
        assert probe["schema"] == "metrics.probe_histogram.v1"
        assert probe["buckets"][0] == {"distance": 0, "count": 4}

        heatmap = json.loads(urlopen(f"http://127.0.0.1:{port}/api/metrics/heatmap", timeout=0.5).read())
        assert heatmap["schema"] == "metrics.key_heatmap.v1"
        assert heatmap["total"] == 6
        assert heatmap["matrix"] == [[4, 2]]
    finally:
        server.shutdown()
        server.server_close()


def test_collect_key_heatmap_tracks_counts() -> None:
    table = cli.TwoLevelChainingMap(initial_buckets=4, groups_per_bucket=2)
    for idx in range(6):
        table.put(f"k{idx}", idx)
    heatmap = cli.collect_key_heatmap(table, target_cols=4, max_cells=4)
    assert heatmap["total"] == 6
    assert heatmap["rows"] >= 1
    assert heatmap["matrix"]
    # slot span should be at least one and aggregated cells should sum to total
    flattened = [value for row in heatmap["matrix"] for value in row]
    assert sum(flattened) == 6
