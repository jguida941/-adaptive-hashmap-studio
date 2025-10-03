"""Textual TUI for Adaptive Hash Map metrics."""

from __future__ import annotations

import asyncio
import json
import math
import socket
from datetime import datetime
from itertools import pairwise
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_TEXTUAL_ERR: Optional[Exception] = None
try:  # pragma: no cover - import guarded for environments without Textual
    from textual.app import App, ComposeResult  # type: ignore[import-not-found]
    from textual.binding import Binding  # type: ignore[import-not-found]
    from textual.reactive import reactive  # type: ignore[import-not-found]
    from textual.widgets import Footer, Header, Static  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover
    _TEXTUAL_ERR = exc
    App = cast(Any, object)
    ComposeResult = cast(Any, object)
    Binding = cast(Any, object)
    reactive = cast(Any, lambda default: default)
    Footer = cast(Any, object)
    Header = cast(Any, object)
    Static = cast(Any, object)


def fetch_metrics(endpoint: str, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
    """Return the latest metrics JSON from ``endpoint`` or ``None`` on error."""

    request = Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec: B310 (local HTTP only)
            payload = response.read()
    except (HTTPError, URLError, TimeoutError, socket.timeout, ConnectionError):
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def fetch_history(endpoint: str, timeout: float = 1.0) -> Optional[List[Dict[str, Any]]]:
    request = Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec: B310
            payload = response.read()
    except (HTTPError, URLError, TimeoutError, socket.timeout, ConnectionError):
        return None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _format_latency(packet: Dict[str, Any]) -> str:
    pieces = []
    for key in ("p50", "p90", "p99"):
        value = _safe_float(packet.get(key))
        label = key.upper()
        pieces.append(f"{label}: {value:.3f} ms" if value is not None else f"{label}: n/a")
    return "  ".join(pieces)


def _format_alerts(alerts: Any) -> str:
    if not isinstance(alerts, list) or not alerts:
        return "No active alerts."
    lines = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        prefix = "🚩" if alert.get("severity") == "warning" else "⚠"
        metric = alert.get("metric", "metric")
        message = alert.get("message") or f"Guardrail triggered: {metric}"
        lines.append(f"{prefix} {message}")
    return "\n".join(lines) if lines else "No active alerts."


def _format_summary(tick: Dict[str, Any]) -> str:
    backend = tick.get("backend", "unknown")
    ops = int(tick.get("ops", 0))
    ops_by_type = tick.get("ops_by_type", {}) if isinstance(tick.get("ops_by_type"), dict) else {}
    puts = int(ops_by_type.get("put", 0))
    gets = int(ops_by_type.get("get", 0))
    dels = int(ops_by_type.get("del", 0))
    load_factor = _safe_float(tick.get("load_factor"))
    tombstones = _safe_float(tick.get("tombstone_ratio"))
    avg_probe = _safe_float(tick.get("avg_probe_estimate"))
    max_group_len = _safe_float(tick.get("max_group_len"))
    migrations = int(tick.get("migrations", 0))
    compactions = int(tick.get("compactions", 0))
    latency_packet = {}
    latency = tick.get("latency_ms")
    if isinstance(latency, dict):
        packet = latency.get("overall")
        if isinstance(packet, dict):
            latency_packet = packet

    def fmt(value: Optional[float], precision: int = 3) -> str:
        return f"{value:.{precision}f}" if value is not None else "n/a"

    lines = [
        f"Backend: {backend}",
        f"Ops: {ops:,} (put {puts:,} | get {gets:,} | del {dels:,})",
        (
            f"Load factor: {fmt(load_factor)}  Tombstones: {fmt(tombstones)}\n"
            f"Avg probe: {fmt(avg_probe, 2)}  Max group len: {fmt(max_group_len, 1)}"
        ),
        f"Migrations: {migrations}  Compactions: {compactions}",
    ]
    if latency_packet:
        lines.append(f"Latency → {_format_latency(latency_packet)}")
    return "\n".join(lines)


def _format_history(history: Iterable[Dict[str, Any]]) -> str:
    items = list(history)[-10:]
    if not items:
        return "History window empty — waiting for samples."

    load_series = [val for val in (_safe_float(item.get("load_factor")) for item in items) if val is not None]
    load_line = "Load factor trend: " + (
        "  ".join(f"{val:.2f}" for val in load_series) if load_series else "n/a"
    )

    throughputs: List[float] = []
    for prev, curr in pairwise(items):
        t0 = _safe_float(prev.get("t"))
        t1 = _safe_float(curr.get("t"))
        if t0 is None or t1 is None or t1 <= t0:
            continue
        d_ops = int(curr.get("ops", 0)) - int(prev.get("ops", 0))
        throughputs.append(max(d_ops, 0) / (t1 - t0))
    if throughputs:
        recent_tp = throughputs[-1]
        tp_line = f"Recent throughput: {recent_tp:,.0f} ops/s"
    else:
        tp_line = "Recent throughput: n/a"

    migrations = int(items[-1].get("migrations", 0))
    events_line = f"Migrations so far: {migrations}"

    return "\n".join([load_line, tp_line, events_line])


if _TEXTUAL_ERR is None:
    class AdaptiveMetricsApp(App[None]):
        """Minimal Textual application that polls and renders Adaptive Hash Map metrics."""

        latest_tick: reactive[Optional[Dict[str, Any]]] = reactive(None)
        last_updated: reactive[Optional[datetime]] = reactive(None)

        CSS = """
        Screen { layout: vertical; }
        #status { padding: 1 2; background: #1f2937; color: #e5e7eb; }
        #summary { padding: 1 2; }
        #history { padding: 1 2; color: #94a3b8; }
        #alerts { padding: 1 2; color: #f97316; }
        """

        BINDINGS = [Binding("r", "refresh", "Refresh"), Binding("q", "quit", "Quit")]

        def __init__(
            self,
            metrics_endpoint: str,
            history_endpoint: Optional[str] = None,
            poll_interval: float = 2.0,
            timeout: float = 1.0,
        ) -> None:
            super().__init__()
            self.metrics_endpoint = metrics_endpoint
            self.history_endpoint = history_endpoint
            self.poll_interval = poll_interval
            self.timeout = timeout

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("Waiting for metrics…", id="status")
            yield Static("", id="summary")
            yield Static("", id="history")
            yield Static("", id="alerts")
            yield Footer()

        async def on_mount(self) -> None:
            self._summary = self.query_one("#summary", Static)
            self._status = self.query_one("#status", Static)
            self._history = self.query_one("#history", Static)
            self._alerts = self.query_one("#alerts", Static)
            self.set_interval(self.poll_interval, self._poll_and_render)
            await self._poll_and_render(initial=True)

        async def action_refresh(self) -> None:  # noqa: D401 - Textual action signature
            await self._poll_and_render()

        async def _poll_and_render(self, initial: bool = False) -> None:
            tick, history, error = await self._fetch_tick_and_history()
            now = datetime.now()
            if tick is not None:
                self.latest_tick = tick
                self.last_updated = now
                self._summary.update(_format_summary(tick))
                self._alerts.update(_format_alerts(tick.get("alerts")))
                self._status.update(
                    f"Last update: {now.strftime('%H:%M:%S')} • Source: {self.metrics_endpoint}"
                )
                if history is not None:
                    self._history.update(_format_history(history))
            else:
                message = error or "No metrics payload yet; ensure a run is active."
                if self.latest_tick is None:
                    self._summary.update("Waiting for metrics…")
                    self._history.update("History window empty — waiting for samples.")
                    self._alerts.update("")
                self._status.update(message)
                if initial:
                    self._status.update(
                        f"Waiting for metrics at {self.metrics_endpoint}. Launch `hashmap_cli.py` with"
                        " `--metrics-port` to start streaming."
                    )

        async def _fetch_tick_and_history(
            self,
        ) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]], Optional[str]]:
            loop = asyncio.get_running_loop()

            def _load() -> Optional[Dict[str, Any]]:
                return fetch_metrics(self.metrics_endpoint, timeout=self.timeout)

            tick = await loop.run_in_executor(None, _load)
            if tick is None:
                return None, None, None
            if tick.get("schema") not in {None, "metrics.v1"}:
                return None, None, f"Unsupported schema: {tick.get('schema')}"

            history_data: Optional[List[Dict[str, Any]]] = None
            endpoint = self.history_endpoint
            if endpoint is None and "/api/metrics" in self.metrics_endpoint:
                base = self.metrics_endpoint.rsplit("/api/metrics", 1)[0]
                endpoint = f"{base}/api/metrics/history?limit=120"
            if endpoint is not None:
                history_data = await loop.run_in_executor(
                    None, lambda: fetch_history(endpoint, timeout=self.timeout)
                )

            return tick, history_data or [], None
else:  # pragma: no cover - exercised only when Textual is absent
    class AdaptiveMetricsApp:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "The Textual TUI requires the 'textual' extra. Install with `pip install .[ui]`."
            ) from _TEXTUAL_ERR


def run_tui(
    metrics_endpoint: str = "http://127.0.0.1:9090/api/metrics",
    history_endpoint: Optional[str] = None,
    poll_interval: float = 2.0,
    timeout: float = 1.0,
) -> None:
    """Launch the Textual TUI against the given metrics endpoint."""

    app = AdaptiveMetricsApp(
        metrics_endpoint=metrics_endpoint,
        history_endpoint=history_endpoint,
        poll_interval=poll_interval,
        timeout=timeout,
    )
    app.run()


__all__ = [
    "AdaptiveMetricsApp",
    "fetch_metrics",
    "run_tui",
]
