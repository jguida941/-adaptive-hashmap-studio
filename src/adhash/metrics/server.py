from __future__ import annotations

import csv
import gzip
import io
import json
import logging
import os
import threading
import time
from html import escape
from importlib import resources
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple, cast
from urllib.parse import ParseResult, parse_qs, urlparse

from .constants import (
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    ALLOW_ORIGIN,
    CACHE_CONTROL,
    ERROR_SCHEMA,
    EVENTS_SCHEMA,
    HEALTH_SCHEMA,
    HISTORY_SCHEMA,
    JSON_CONTENT_TYPE,
    KEY_HEATMAP_SCHEMA,
    LATENCY_HISTOGRAM_SCHEMA,
    PROBE_HISTOGRAM_SCHEMA,
    PROMETHEUS_CONTENT_TYPE,
    TOKEN_ENV_VAR,
    VARY_HEADER,
)
from .core import Metrics

logger = logging.getLogger("hashmap_cli")





def start_metrics_server(
    metrics: Metrics,
    port: int,
    host: str = "127.0.0.1",
    *,
    comparison: Optional[Dict[str, Any]] = None,
) -> Tuple[HTTPServer, Callable[[], None]]:
    class Handler(BaseHTTPRequestHandler):
        api_token = os.getenv(TOKEN_ENV_VAR)
        comparison_payload = comparison
        server_version = "AdaptiveHashMap"
        sys_version = ""

        def _set_common_headers(self, *, content_type: str, length: int, gzip_enabled: bool = False) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", CACHE_CONTROL)
            self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", ALLOWED_METHODS)
            self.send_header("Access-Control-Allow-Headers", ALLOWED_HEADERS)
            self.send_header("Vary", VARY_HEADER)
            if gzip_enabled:
                self.send_header("Content-Encoding", "gzip")

        def _write_body(
            self,
            body: bytes,
            content_type: str,
            *,
            gzip_enabled: bool = False,
            status: int = 200,
        ) -> None:
            self.send_response(status)
            self._set_common_headers(content_type=content_type, length=len(body), gzip_enabled=gzip_enabled)
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def _client_supports_gzip(self) -> bool:
            header = self.headers.get("Accept-Encoding") or ""
            encodings = [entry.strip() for entry in header.split(",") if entry.strip()]
            for encoding in encodings:
                parts = [part.strip() for part in encoding.split(";") if part.strip()]
                if not parts:
                    continue
                name = parts[0].lower()
                if name != "gzip":
                    continue
                q = 1.0
                for param in parts[1:]:
                    if param.lower().startswith("q="):
                        try:
                            q = float(param[2:])
                        except ValueError:
                            q = 0.0
                if q > 0.0:
                    return True
            return False

        def _write_json(self, payload: Any, status: int = 200) -> None:
            raw = json.dumps(payload).encode("utf-8")
            gzip_enabled = self._client_supports_gzip()
            body = gzip.compress(raw) if gzip_enabled else raw
            self._write_body(body, JSON_CONTENT_TYPE, gzip_enabled=gzip_enabled, status=status)

        def _unauthorized(self) -> None:
            self._write_json(
                {
                    "schema": ERROR_SCHEMA,
                    "generated_at": time.time(),
                    "error": "unauthorized",
                },
                status=401,
            )

        def _authorized(self) -> bool:
            token = Handler.api_token
            if not token:
                return True
            header = self.headers.get("Authorization")
            if header == f"Bearer {token}":
                return True
            parsed = urlparse(self.path)
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            return query_token == token

        def _limit(self, parsed: ParseResult, default: int, *, clamp: Optional[int] = None) -> int:
            try:
                value = int(parse_qs(parsed.query).get("limit", [str(default)])[0])
            except ValueError:
                value = default
            value = max(1, value)
            if clamp is not None:
                value = min(value, clamp)
            return value

        def _history_rows(self, limit: int) -> List[Dict[str, Any]]:
            history_buffer = cast(Optional[Deque[Dict[str, Any]]], getattr(metrics, "history_buffer", None))
            if history_buffer is not None:
                return [tick for tick in list(history_buffer)[-limit:] if isinstance(tick, dict)]
            latest = getattr(metrics, "latest_tick", None)
            return [latest] if isinstance(latest, dict) else []

        def _serve_health(self) -> None:
            self._write_json(
                {
                    "schema": HEALTH_SCHEMA,
                    "generated_at": time.time(),
                    "status": "ok",
                }
            )

        def _serve_metrics_prometheus(self) -> None:
            body = metrics.render().encode("utf-8")
            self._write_body(body, PROMETHEUS_CONTENT_TYPE)

        def _serve_metrics_summary(self) -> None:
            payload = metrics.build_summary_payload()
            self._write_json(payload)

        def _serve_comparison(self) -> None:
            comparison_payload = Handler.comparison_payload
            if comparison_payload is None:
                self._write_json(
                    {
                        "schema": "adhash.compare.none",
                        "generated_at": time.time(),
                        "detail": "comparison data not loaded",
                    },
                    status=404,
                )
            else:
                self._write_json(comparison_payload)

        def _serve_events(self, parsed: ParseResult) -> None:
            limit = self._limit(parsed, 100, clamp=512)
            events = list(getattr(metrics, "events_history", []))[-limit:]
            self._write_json(
                {
                    "schema": EVENTS_SCHEMA,
                    "generated_at": time.time(),
                    "events": events,
                }
            )

        def _serve_metrics_history_json(self, parsed: ParseResult) -> None:
            limit = self._limit(parsed, 100)
            data = self._history_rows(limit)
            self._write_json(
                {
                    "schema": HISTORY_SCHEMA,
                    "generated_at": time.time(),
                    "items": data,
                }
            )

        def _serve_metrics_history_csv(self, parsed: ParseResult) -> None:
            limit = self._limit(parsed, default=1200)
            rows = self._history_rows(limit)
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "t",
                    "ops",
                    "ops_per_second_ema",
                    "ops_per_second_instant",
                    "load_factor",
                    "avg_probe_estimate",
                    "tombstone_ratio",
                    "backend",
                    "state",
                    "events",
                ]
            )
            for tick in rows:
                events_payload = tick.get("events")
                event_summary = ""
                if isinstance(events_payload, list):
                    event_summary = ";".join(
                        f"{(evt or {}).get('type', 'event')}@{(evt or {}).get('t', '')}"
                        if isinstance(evt, dict)
                        else str(evt)
                        for evt in events_payload
                    )
                writer.writerow(
                    [
                        tick.get("t", ""),
                        tick.get("ops", ""),
                        tick.get("ops_per_second_ema", ""),
                        tick.get("ops_per_second_instant", ""),
                        tick.get("load_factor", ""),
                        tick.get("avg_probe_estimate", ""),
                        tick.get("tombstone_ratio", ""),
                        tick.get("backend", ""),
                        tick.get("state", ""),
                        event_summary,
                    ]
                )
            body = output.getvalue().encode("utf-8")
            self.send_response(200)
            self._set_common_headers(content_type="text/csv; charset=utf-8", length=len(body))
            self.send_header("Content-Disposition", "attachment; filename=timeline.csv")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _serve_latency_histogram(self) -> None:
            latest = getattr(metrics, "latest_tick", None) or {}
            hist = latest.get("latency_hist_ms")
            latency_payload: Dict[str, Any] = {
                "schema": LATENCY_HISTOGRAM_SCHEMA,
                "generated_at": time.time(),
                "preset": latest.get("latency_hist_preset"),
                "operations": hist if isinstance(hist, dict) else {},
            }
            self._write_json(latency_payload)

        def _serve_probe_histogram(self) -> None:
            latest = getattr(metrics, "latest_tick", None) or {}
            raw = latest.get("probe_hist")
            buckets: List[Dict[str, int]] = []
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, (list, tuple)) and len(item) == 2:
                        distance, count = item
                    elif isinstance(item, dict):
                        distance = item.get("distance")
                        count = item.get("count")
                    else:
                        continue
                    try:
                        buckets.append({"distance": int(distance), "count": int(count)})
                    except (TypeError, ValueError):
                        continue
            probe_payload = {
                "schema": PROBE_HISTOGRAM_SCHEMA,
                "generated_at": time.time(),
                "buckets": buckets,
            }
            self._write_json(probe_payload)

        def _serve_heatmap(self) -> None:
            latest = getattr(metrics, "latest_tick", None) or {}
            heatmap = getattr(metrics, "key_heatmap", None)
            if not isinstance(heatmap, dict):
                heatmap = latest.get("key_heatmap") if isinstance(latest, dict) else {}
            heatmap_payload = {
                "schema": KEY_HEATMAP_SCHEMA,
                "generated_at": time.time(),
                "rows": heatmap.get("rows", 0) if isinstance(heatmap, dict) else 0,
                "cols": heatmap.get("cols", 0) if isinstance(heatmap, dict) else 0,
                "matrix": heatmap.get("matrix", []) if isinstance(heatmap, dict) else [],
                "total": heatmap.get("total", 0) if isinstance(heatmap, dict) else 0,
                "max": heatmap.get("max", 0) if isinstance(heatmap, dict) else 0,
                "slot_span": heatmap.get("slot_span", 1) if isinstance(heatmap, dict) else 1,
                "original_slots": heatmap.get("original_slots", 0) if isinstance(heatmap, dict) else 0,
            }
            self._write_json(heatmap_payload)

        def _serve_dashboard(self, parsed: ParseResult) -> None:
            body = self._render_dashboard_html()
            self._write_body(body, "text/html; charset=utf-8")

        def _serve_static_asset(self, path: str) -> None:
            asset = path[len("/static/") :]
            if not asset or "/" in asset or ".." in asset:
                self._respond_not_found(path)
                return
            try:
                data = resources.files("adhash.metrics.static").joinpath(asset).read_bytes()
            except (FileNotFoundError, OSError):
                self._respond_not_found(path)
                return
            if asset.endswith(".css"):
                mime = "text/css; charset=utf-8"
            elif asset.endswith(".js"):
                mime = "application/javascript; charset=utf-8"
            else:
                mime = "application/octet-stream"
            self._write_body(data, mime)

        def _respond_not_found(self, path: str) -> None:
            self._write_json(
                {
                    "schema": ERROR_SCHEMA,
                    "generated_at": time.time(),
                    "error": "not_found",
                    "path": path,
                },
                status=404,
            )

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", ALLOW_ORIGIN)
            self.send_header("Access-Control-Allow-Methods", ALLOWED_METHODS)
            self.send_header("Access-Control-Allow-Headers", ALLOWED_HEADERS)
            self.send_header("Cache-Control", CACHE_CONTROL)
            self.end_headers()

        def do_GET(self) -> None:
            if not self._authorized():
                self._unauthorized()
                return
            parsed = urlparse(self.path)
            path = parsed.path
            if path in {"/healthz", "/readyz"}:
                self._serve_health()
                return
            if path == "/metrics":
                self._serve_metrics_prometheus()
                return
            if path == "/api/metrics":
                self._serve_metrics_summary()
                return
            if path == "/api/compare":
                self._serve_comparison()
                return
            if path == "/api/events":
                self._serve_events(parsed)
                return
            if path == "/api/metrics/history":
                self._serve_metrics_history_json(parsed)
                return
            if path == "/api/metrics/history.csv":
                self._serve_metrics_history_csv(parsed)
                return
            if path == "/api/metrics/histogram/latency":
                self._serve_latency_histogram()
                return
            if path == "/api/metrics/histogram/probe":
                self._serve_probe_histogram()
                return
            if path == "/api/metrics/heatmap":
                self._serve_heatmap()
                return
            if path in {"/", "/index.html"}:
                self._serve_dashboard(parsed)
                return
            if path.startswith("/static/"):
                self._serve_static_asset(path)
                return
            self._respond_not_found(path)

        def _render_dashboard_html(self) -> bytes:
            token_meta = ""

            if Handler.api_token:
                token_meta = f'<meta name="adhash-token" content="{escape(Handler.api_token, quote=True)}"/>'
            template = resources.files("adhash.metrics.static").joinpath("dashboard.html").read_text(encoding="utf-8")
            return template.replace("<!--__TOKEN_META__-->", token_meta).encode("utf-8")


        def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - suppress noisy logs
            return

    Handler.api_token = os.getenv(TOKEN_ENV_VAR)
    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(
        "Metrics server: http://%s:%d/  (dashboard) and /metrics",
        host.replace("127.0.0.1", "localhost"),
        port,
    )

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)

    return server, stop


__all__ = ["start_metrics_server"]
