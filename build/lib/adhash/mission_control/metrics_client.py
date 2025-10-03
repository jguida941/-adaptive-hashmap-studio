# mypy: ignore-errors
"""Async metrics client for Mission Control."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from urllib.request import Request, urlopen


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
        req = Request(f"{self.base_url}{path}", headers={"Accept": "application/json"})
        with urlopen(req, timeout=1.0) as resp:  # nosec B310 local HTTP
            payload = resp.read()
        return json.loads(payload.decode("utf-8"))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                tick = self._fetch_json("/api/metrics")
                latency = self._fetch_json("/api/metrics/histogram/latency")
                probe = self._fetch_json("/api/metrics/histogram/probe")
                heatmap = self._fetch_json("/api/metrics/heatmap")
                events = self._fetch_json("/api/events?limit=100")
                snapshot = MetricsSnapshot(
                    tick=tick if isinstance(tick, dict) else {},
                    latency=latency if isinstance(latency, dict) else {},
                    probe=probe if isinstance(probe, dict) else {},
                    heatmap=heatmap if isinstance(heatmap, dict) else {},
                    events=events if isinstance(events, list) else [],
                )
                if self.on_snapshot:
                    self.on_snapshot(snapshot)
            except Exception as exc:  # noqa: BLE001
                if self.on_error:
                    self.on_error(exc)
            finally:
                time.sleep(self.interval)
        self._thread = None
