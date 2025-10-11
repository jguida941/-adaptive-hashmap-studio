# mypy: ignore-errors
"""Async metrics client for Mission Control."""

from __future__ import annotations

import gzip
import ipaddress
import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from adhash.metrics import AUTH_HEADER, TOKEN_ENV_VAR


@dataclass
class MetricsSnapshot:
    tick: dict[str, Any]
    latency: dict[str, Any]
    probe: dict[str, Any]
    heatmap: dict[str, Any]
    events: list[dict[str, Any]]


class HttpPoller:
    """Simple polling loop that fetches mission control endpoints on a background thread."""

    def __init__(self, host: str, port: int, interval: float = 2.0) -> None:
        self.base_url = self._build_base_url(host, port)
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.on_snapshot: Callable[[MetricsSnapshot], None] | None = None
        self.on_error: Callable[[Exception], None] | None = None
        self._token = os.getenv(TOKEN_ENV_VAR)

    @staticmethod
    def _build_base_url(host: str, port: int) -> str:
        if not isinstance(port, int):
            raise TypeError("Port must be an integer")
        if port <= 0 or port >= 65536:
            raise ValueError(f"Port must be between 1 and 65535; got {port}")

        if host is None:
            raise ValueError("Host must be provided for Mission Control metrics polling")
        host_normalized = host.strip()
        if not host_normalized:
            raise ValueError("Host must be a non-empty string")
        host_normalized = host_normalized.rstrip("/")
        if "://" in host_normalized:
            raise ValueError(f"Host should not include a scheme; got {host!r}")
        bracketed = host_normalized.startswith("[") and host_normalized.endswith("]")
        literal_host = host_normalized[1:-1] if bracketed else host_normalized
        if not literal_host:
            raise ValueError("Host must be a non-empty string")
        try:
            ip_obj = ipaddress.ip_address(literal_host)
        except ValueError:
            if ":" in literal_host:
                raise ValueError(f"Host should not include a port; got {host!r}") from None
            netloc_host = literal_host
        else:
            if isinstance(ip_obj, ipaddress.IPv6Address):
                netloc_host = f"[{ip_obj.compressed}]"
            else:
                netloc_host = ip_obj.compressed

        candidate = f"http://{netloc_host}:{port}"
        parsed = urlparse(candidate)
        if not parsed.hostname:
            raise ValueError("Hostname must be provided for Mission Control metrics polling")
        return candidate.rstrip("/")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        self._thread = None

    def _fetch_json(self, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError(f"Expected path starting with '/'; got {path!r}")
        headers = {"Accept": "application/json"}
        if self._token:
            headers[AUTH_HEADER] = f"Bearer {self._token}"
        target = urljoin(self.base_url, path)
        req = Request(target, headers=headers)  # noqa: S310  # nosec B310
        with urlopen(req, timeout=1.0) as resp:  # noqa: S310  # nosec B310
            payload = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                payload = gzip.decompress(payload)
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _as_dict(payload: Any) -> dict[str, Any]:
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _as_list(payload: Any, key: str) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            data = payload.get(key)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                tick_payload = self._fetch_json("/api/metrics")
                latency = self._fetch_json("/api/metrics/histogram/latency")
                probe = self._fetch_json("/api/metrics/histogram/probe")
                heatmap = self._fetch_json("/api/metrics/heatmap")
                events_payload = self._fetch_json("/api/events?limit=100")
                snapshot = MetricsSnapshot(
                    tick=self._as_dict(tick_payload),
                    latency=latency if isinstance(latency, dict) else {},
                    probe=probe if isinstance(probe, dict) else {},
                    heatmap=heatmap if isinstance(heatmap, dict) else {},
                    events=self._as_list(events_payload, "events"),
                )
                if self.on_snapshot:
                    self.on_snapshot(snapshot)
            except Exception as exc:  # noqa: BLE001
                if self.on_error:
                    self.on_error(exc)
            finally:
                time.sleep(self.interval)
        self._thread = None
