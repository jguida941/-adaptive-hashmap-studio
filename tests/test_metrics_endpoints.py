from __future__ import annotations

import gzip
import json
import time
from collections import deque
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest

from adhash.core.maps import TwoLevelChainingMap, collect_key_heatmap
from adhash.metrics import (
    ALLOW_ORIGIN,
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    CACHE_CONTROL,
    ERROR_SCHEMA,
    EVENTS_SCHEMA,
    JSON_CONTENT_TYPE,
    KEY_HEATMAP_SCHEMA,
    LATENCY_HISTOGRAM_SCHEMA,
    PROBE_HISTOGRAM_SCHEMA,
    SUMMARY_SCHEMA,
    TICK_SCHEMA,
    VARY_HEADER,
    Metrics,
    start_metrics_server,
)


def wait_for_server(
    port: int, retries: int = 10, delay: float = 0.05, headers: dict[str, str] | None = None
) -> None:
    """Helper to wait until the HTTP server starts accepting connections."""

    for _ in range(retries):
        try:
            request = Request(
                f"http://127.0.0.1:{port}/api/metrics",
                headers=headers or {"Accept": "application/json"},
            )
            with urlopen(request, timeout=0.1):  # noqa: S310
                return
        except HTTPError as exc:
            if exc.code == 401:
                return
            time.sleep(delay)
        except (URLError, OSError, ConnectionError):
            time.sleep(delay)
    raise RuntimeError("metrics server did not start in time")


def test_histogram_endpoints_expose_json() -> None:
    metrics_payload: dict[str, Any] = {
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
        wait_for_server(
            port, headers={"Authorization": "Bearer secret", "Accept": "application/json"}
        )

        def read_json(path: str) -> dict[str, Any]:
            with urlopen(path, timeout=0.5) as response:  # noqa: S310
                payload = response.read()
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    payload = gzip.decompress(payload)
            return cast(dict[str, Any], json.loads(payload.decode("utf-8")))

        latency = read_json(f"http://127.0.0.1:{port}/api/metrics/histogram/latency")
        assert latency["schema"] == LATENCY_HISTOGRAM_SCHEMA
        assert latency["operations"]["overall"][0]["count"] == 3
        assert latency.get("preset") == "default"
        assert "generated_at" in latency

        probe = read_json(f"http://127.0.0.1:{port}/api/metrics/histogram/probe")
        assert probe["schema"] == PROBE_HISTOGRAM_SCHEMA
        assert probe["buckets"][0] == {"distance": 0, "count": 4}
        assert "generated_at" in probe

        heatmap = read_json(f"http://127.0.0.1:{port}/api/metrics/heatmap")
        assert heatmap["schema"] == KEY_HEATMAP_SCHEMA
        assert heatmap["total"] == 6
        assert heatmap["matrix"] == [[4, 2]]
        assert "generated_at" in heatmap
    finally:
        stop_server()


def test_metrics_summary_respects_accept_encoding() -> None:
    metrics_payload: dict[str, Any] = {
        "schema": TICK_SCHEMA,
        "t": 1.0,
        "ops": 10,
        "ops_by_type": {"put": 4, "get": 5, "del": 1},
    }
    metrics = Metrics()
    metrics.latest_tick = metrics_payload

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)

        request_plain = Request(
            f"http://127.0.0.1:{port}/api/metrics",
            headers={"Accept": "application/json"},
        )
        with urlopen(request_plain, timeout=0.5) as response:  # noqa: S310
            plain_body = response.read()
            plain_headers = response.headers
        assert plain_headers.get("Content-Encoding", "").lower() not in {"gzip", "x-gzip"}
        assert plain_headers.get("Cache-Control") == CACHE_CONTROL
        assert plain_headers.get("Access-Control-Allow-Origin") == ALLOW_ORIGIN
        assert plain_headers.get("Access-Control-Allow-Methods") == ALLOWED_METHODS
        assert plain_headers.get("Access-Control-Allow-Headers") == ALLOWED_HEADERS
        assert plain_headers.get("Vary") == VARY_HEADER
        assert plain_headers.get("Content-Type") == JSON_CONTENT_TYPE
        assert plain_headers.get("Content-Length") == str(len(plain_body))
        data = json.loads(plain_body.decode("utf-8"))
        assert data["ops"] == 10
        assert data["schema"] == SUMMARY_SCHEMA
        assert "generated_at" in data
        assert "totals" in data

        request_gzip = Request(
            f"http://127.0.0.1:{port}/api/metrics",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        with urlopen(request_gzip, timeout=0.5) as response:  # noqa: S310
            compressed_body = response.read()
            gzip_headers = response.headers
        assert gzip_headers.get("Content-Encoding", "").lower() == "gzip"
        assert gzip_headers.get("Cache-Control") == CACHE_CONTROL
        assert gzip_headers.get("Access-Control-Allow-Origin") == ALLOW_ORIGIN
        assert gzip_headers.get("Access-Control-Allow-Methods") == ALLOWED_METHODS
        assert gzip_headers.get("Access-Control-Allow-Headers") == ALLOWED_HEADERS
        assert gzip_headers.get("Vary") == VARY_HEADER
        assert gzip_headers.get("Content-Type") == JSON_CONTENT_TYPE
        assert gzip_headers.get("Content-Length") == str(len(compressed_body))
        payload = gzip.decompress(compressed_body)
        data = json.loads(payload.decode("utf-8"))
        assert data["ops"] == 10
        assert data["schema"] == SUMMARY_SCHEMA
        assert "generated_at" in data
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
    metrics.history_buffer.append({
        "t": 0.0,
        "ops": 0,
        "ops_per_second_ema": 100.0,
        "load_factor": 0.1,
        "avg_probe_estimate": 1.2,
        "tombstone_ratio": 0.0,
        "backend": "chaining",
        "state": "running",
    })
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
        with urlopen(
            f"http://127.0.0.1:{port}/api/metrics/history.csv?limit=2", timeout=0.5
        ) as response:  # noqa: S310
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
            urlopen(f"http://127.0.0.1:{port}/", timeout=0.5)  # noqa: S310
        assert exc_info.value.code == 401
        unauthorized_payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert unauthorized_payload["schema"] == ERROR_SCHEMA
        assert unauthorized_payload["error"] == "unauthorized"
        assert "generated_at" in unauthorized_payload

        with urlopen(f"http://127.0.0.1:{port}/?token=secret", timeout=0.5) as response:  # noqa: S310
            html_body = response.read().decode("utf-8")
        assert '<meta name="adhash-token" content="secret"/>' in html_body

        request = Request(
            f"http://127.0.0.1:{port}/api/metrics",
            headers={"Authorization": "Bearer secret", "Accept": "application/json"},
        )
        with urlopen(request, timeout=0.5) as response:  # noqa: S310
            assert response.status == 200
    finally:
        stop_server()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_dashboard_serves_static_assets() -> None:
    metrics = Metrics()

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)

        with urlopen(f"http://127.0.0.1:{port}/static/dashboard.css", timeout=0.5) as response:  # noqa: S310
            assert response.status == 200
            css = response.read().decode("utf-8")
        assert ".charts" in css

        with urlopen(f"http://127.0.0.1:{port}/static/dashboard.js", timeout=0.5) as response:  # noqa: S310
            assert response.status == 200
            js = response.read().decode("utf-8")
        assert "function poll(" in js
    finally:
        stop_server()


def test_metrics_summary_falls_back_to_latest_tick() -> None:
    metrics = Metrics()
    metrics.latest_tick = {
        "schema": TICK_SCHEMA,
        "ops": 123,
        "backend": "adaptive",
    }

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)
        request = Request(
            f"http://127.0.0.1:{port}/api/metrics?limit=5",
            headers={"Accept": "application/json"},
        )
        with urlopen(request, timeout=0.5) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["items"]
        assert payload["items"][0]["schema"] == TICK_SCHEMA
        assert payload["items"][0]["ops"] == 123
        assert payload["schema"] == SUMMARY_SCHEMA
        assert "generated_at" in payload
    finally:
        stop_server()


def test_events_endpoint_applies_limit_and_clamp() -> None:
    metrics = Metrics()
    metrics.events_history = deque([{"idx": idx} for idx in range(600)])

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)

        def fetch(path: str) -> dict[str, Any]:
            with urlopen(path, timeout=0.5) as response:  # noqa: S310
                return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))

        first_event = fetch(f"http://127.0.0.1:{port}/api/events?limit=0")
        assert first_event["schema"] == EVENTS_SCHEMA
        assert "generated_at" in first_event
        assert len(first_event["events"]) == 1
        assert first_event["events"][0]["idx"] == 599

        invalid_value = fetch(f"http://127.0.0.1:{port}/api/events?limit=abc")
        assert invalid_value["schema"] == EVENTS_SCHEMA
        assert "generated_at" in invalid_value
        assert len(invalid_value["events"]) == 100
        assert invalid_value["events"][0]["idx"] == 500

        clamped = fetch(f"http://127.0.0.1:{port}/api/events?limit=9999")
        assert clamped["schema"] == EVENTS_SCHEMA
        assert "generated_at" in clamped
        assert len(clamped["events"]) == 512
        assert clamped["events"][0]["idx"] == 88
        assert clamped["events"][-1]["idx"] == 599
    finally:
        stop_server()


def test_metrics_options_endpoint_exposes_cors_headers() -> None:
    metrics = Metrics()

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)

        request = Request(
            f"http://127.0.0.1:{port}/api/metrics",
            method="OPTIONS",
        )
        with urlopen(request, timeout=0.5) as response:  # noqa: S310
            headers = response.headers
            status = response.status
        assert status == 204
        assert headers.get("Access-Control-Allow-Origin") == ALLOW_ORIGIN
        assert headers.get("Access-Control-Allow-Methods") == ALLOWED_METHODS
        assert headers.get("Access-Control-Allow-Headers") == ALLOWED_HEADERS
        assert headers.get("Cache-Control") == CACHE_CONTROL
    finally:
        stop_server()


def test_static_asset_rejects_directory_escape() -> None:
    metrics = Metrics()

    try:
        server, stop_server = start_metrics_server(metrics, 0)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"http://127.0.0.1:{port}/static/../secrets.txt", timeout=0.5)

        error = exc_info.value
        assert error.code == 404
        headers = error.headers
        assert headers.get("Access-Control-Allow-Origin") == ALLOW_ORIGIN
        assert headers.get("Access-Control-Allow-Methods") == ALLOWED_METHODS
        assert headers.get("Access-Control-Allow-Headers") == ALLOWED_HEADERS
        assert headers.get("Cache-Control") == CACHE_CONTROL
        body = error.read().decode("utf-8")
        payload = json.loads(body)
        assert payload["error"] == "not_found"
        assert payload["path"] == "/static/../secrets.txt"
        assert payload["schema"] == ERROR_SCHEMA
        assert "generated_at" in payload
    finally:
        stop_server()


def test_compare_endpoint_serves_payload_and_not_found() -> None:
    metrics = Metrics()
    comparison_payload = {"schema": "adhash.compare.demo", "items": [{"ops": 3}]}

    try:
        server, stop_server = start_metrics_server(metrics, 0, comparison=comparison_payload)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)
        with urlopen(f"http://127.0.0.1:{port}/api/compare", timeout=0.5) as response:  # noqa: S310
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert payload == comparison_payload
    finally:
        stop_server()

    try:
        server, stop_server = start_metrics_server(metrics, 0, comparison=None)
    except PermissionError:
        pytest.skip("network bindings not permitted in sandbox")
    try:
        port = server.server_address[1]
        wait_for_server(port)
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"http://127.0.0.1:{port}/api/compare", timeout=0.5)  # noqa: S310
        assert exc_info.value.code == 404
        error_payload = json.loads(exc_info.value.read().decode("utf-8"))
        assert error_payload["schema"] == "adhash.compare.none"
        assert error_payload["detail"] == "comparison data not loaded"
        assert "generated_at" in error_payload
    finally:
        stop_server()
