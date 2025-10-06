# mypy: ignore-errors
"""Async metrics client for Mission Control."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.request import Request, urlopen
import gzip

from adhash.metrics import AUTH_HEADER, TOKEN_ENV_VAR


@dataclass
class MetricsSnapshot:
    tick: Dict[str, Any]
    latency: Dict[str, Any]
    probe: Dict[str, Any]
    heatmap: Dict[str, Any]
    events: list[Dict[str, Any]]


class HttpPoller:
    """Simple polling loop that fetches mission control endpoints on a background thread."""

    def __init__(self, host: str, port: int, interval: float = 2.0) -> None:
        self.base_url = f"http://{host}:{port}"
        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.on_snapshot: Optional[Callable[[MetricsSnapshot], None]] = None
        self.on_error: Optional[Callable[[Exception], None]] = None
        self._token = os.getenv(TOKEN_ENV_VAR)

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
        headers = {"Accept": "application/json"}
        if self._token:
            headers[AUTH_HEADER] = f"Bearer {self._token}"
        req = Request(f"{self.base_url}{path}", headers=headers)
        with urlopen(req, timeout=1.0) as resp:  # nosec B310 local HTTP
            payload = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                payload = gzip.decompress(payload)
        return json.loads(payload.decode("utf-8"))

    @staticmethod
    def _as_dict(payload: Any) -> Dict[str, Any]:
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _as_list(payload: Any, key: str) -> list[Dict[str, Any]]:
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
