"""Textual TUI for Adaptive Hash Map metrics."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import math
import os
import socket
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from adhash.analysis import format_trace_lines
from adhash.metrics import SUMMARY_SCHEMA, TICK_SCHEMA

logger = logging.getLogger(__name__)

_CLIENT_USER_AGENT = "AdaptiveHashMapCLI/1.0"
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB cap to prevent runaway responses.
_LOOPBACK_HOST_LABELS = {"localhost"}

_TEXTUAL_ERR: Exception | None = None
if TYPE_CHECKING:  # pragma: no cover - only for static analysis
    from textual.app import App as AppBase
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.reactive import reactive
    from textual.widgets import Footer, Header, Static
else:  # pragma: no cover - guarded runtime import
    try:
        from textual.app import App as AppBase  # type: ignore[import-not-found]
        from textual.app import ComposeResult
        from textual.binding import Binding  # type: ignore[import-not-found]
        from textual.reactive import reactive  # type: ignore[import-not-found]
        from textual.widgets import Footer, Header, Static  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover  # noqa: BLE001
        _TEXTUAL_ERR = exc
        AppBase = cast(Any, object)
        ComposeResult = cast(Any, object)
        Binding = cast(Any, object)
        reactive = cast(Any, lambda default=None: default)
        Footer = cast(Any, object)
        Header = cast(Any, object)
        Static = cast(Any, object)

ALLOWED_ENDPOINT_SCHEMES = {"http", "https"}


def _env_allows_localhost() -> bool:
    value = os.getenv("ADHASH_ALLOW_LOCALHOST", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _effective_allow_localhost(flag: bool | None) -> bool:
    return _env_allows_localhost() if flag is None else flag


def _env_allows_private() -> bool:
    value = os.getenv("ADHASH_ALLOW_PRIVATE_IPS", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _effective_allow_private(flag: bool | None) -> bool:
    return _env_allows_private() if flag is None else flag


def _is_local_host(hostname: str) -> bool:
    """Return ``True`` if ``hostname`` refers to a loopback or unspecified address."""

    if not hostname:
        return False
    try:
        ip_obj = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname.lower() in _LOOPBACK_HOST_LABELS
    return ip_obj.is_loopback or ip_obj.is_unspecified


def _content_type_allows_json(content_type: str) -> bool:
    """Return ``True`` if the response ``Content-Type`` is JSON or plain text."""

    if not content_type:
        return True
    lowered = content_type.lower()
    return "json" in lowered or lowered.startswith("text/")


def _charset_from_content_type(content_type: str) -> str | None:
    """Extract a ``charset`` parameter from ``Content-Type`` if present."""

    if not content_type:
        return None
    for part in content_type.split(";"):
        part = part.strip()
        if part.lower().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip('"').strip("'")
            if charset:
                return charset
    return None


def _ensure_ip_allowed(
    address: str | ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_localhost: bool,
    allow_private: bool,
) -> None:
    if isinstance(address, ipaddress.IPv4Address | ipaddress.IPv6Address):
        ip_obj = address
    else:
        try:
            ip_obj = ipaddress.ip_address(address)
        except ValueError as exc:
            raise ValueError(f"Unable to parse IP address '{address}'") from exc
    if ip_obj.is_loopback:
        if allow_localhost:
            return
        raise ValueError("Endpoints targeting localhost are not allowed")
    if ip_obj.is_private and not allow_private:
        raise ValueError("Endpoint host resolves to a private address")
    if ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified:
        raise ValueError("Endpoint host resolves to an internal address")


def _resolve_hostname(hostname: str, port: int | None) -> tuple[tuple[Any, ...], ...]:
    return tuple(socket.getaddrinfo(hostname, port))


def _validated_endpoint(
    endpoint: str, *, allow_localhost: bool | None = None, allow_private: bool | None = None
) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme.lower() not in ALLOWED_ENDPOINT_SCHEMES:
        raise ValueError(f"Unsupported endpoint scheme '{parsed.scheme}' (allowed: http, https)")
    if not parsed.netloc:
        raise ValueError("Endpoint must include a host")
    hostname = parsed.hostname or ""
    local_ok = _effective_allow_localhost(allow_localhost)
    private_ok = _effective_allow_private(allow_private)
    if not local_ok and _is_local_host(hostname):
        raise ValueError("Endpoints targeting localhost are not allowed")
    try:
        infos = _resolve_hostname(hostname, parsed.port or None)
    except (TimeoutError, socket.gaierror) as exc:
        raise ValueError(f"Endpoint host '{hostname}' cannot be resolved") from exc
    parsed_any = False
    for info in infos:
        address = info[4][0]
        try:
            ip_obj = ipaddress.ip_address(address)
        except ValueError:
            continue
        parsed_any = True
        _ensure_ip_allowed(ip_obj, allow_localhost=local_ok, allow_private=private_ok)
    if not parsed_any:
        raise ValueError(f"Endpoint host '{hostname}' did not yield any valid IP addresses")
    return endpoint


def _response_is_trusted(
    response: Any, *, allow_localhost: bool | None = None, allow_private: bool | None = None
) -> bool:
    local_ok = _effective_allow_localhost(allow_localhost)
    private_ok = _effective_allow_private(allow_private)
    geturl = getattr(response, "geturl", None)
    if callable(geturl):
        final_url = geturl()
        if isinstance(final_url, str):
            try:
                _validated_endpoint(final_url, allow_localhost=local_ok, allow_private=private_ok)
            except ValueError:
                return local_ok
    raw = getattr(response, "fp", None)
    if raw is not None:
        raw = getattr(raw, "raw", raw)
        sock = getattr(raw, "_sock", None) or getattr(raw, "socket", None)
        if sock is not None:
            try:
                peer = sock.getpeername()
            except OSError:
                peer = None
            if peer:
                address = peer[0] if isinstance(peer, tuple) else peer
                try:
                    _ensure_ip_allowed(address, allow_localhost=local_ok, allow_private=private_ok)
                except ValueError:
                    return False
    return True


def _read_json_response(
    request: Request,
    timeout: float,
    *,
    allow_localhost: bool | None = None,
    allow_private: bool | None = None,
) -> tuple[bytes, str] | None:
    """Fetch a JSON/text response with basic safety validation."""

    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310  # noqa: S310
            if not _response_is_trusted(
                response, allow_localhost=allow_localhost, allow_private=allow_private
            ):
                return None
            headers = getattr(response, "headers", None)
            header_get = getattr(headers, "get", None) if headers is not None else None
            if callable(header_get):
                content_type = header_get("Content-Type", "") or ""
            else:
                getheader = getattr(response, "getheader", None)
                content_type = getheader("Content-Type", "") if callable(getheader) else ""
                if content_type is None:
                    content_type = ""
            if not _content_type_allows_json(content_type):
                return None
            reader = getattr(response, "read", None)
            if not callable(reader):
                return None
            try:
                payload = reader(_MAX_RESPONSE_BYTES + 1)
            except TypeError:
                payload = reader()
            if payload is None:
                return None
            if not isinstance(payload, bytes | bytearray):
                return None
            if len(payload) > _MAX_RESPONSE_BYTES:
                return None
            encoding = "utf-8"
            charset_getter = (
                getattr(headers, "get_content_charset", None) if headers is not None else None
            )
            if callable(charset_getter):
                detected = charset_getter()
                if isinstance(detected, str) and detected:
                    encoding = detected
            if encoding == "utf-8" and content_type:
                charset = _charset_from_content_type(content_type)
                if charset:
                    encoding = charset
            payload_bytes = bytes(payload)
            return payload_bytes, encoding
    except PermissionError:
        return None
    except (HTTPError, URLError, TimeoutError, ConnectionError, OSError) as exc:
        logger.debug("Network fetch failed: %s", exc)
        return None


T = TypeVar("T")


def _call_with_network_flags(
    func: Callable[..., T],
    endpoint: str,
    timeout: float,
    allow_localhost: bool | None,
    allow_private: bool | None,
) -> T:
    """Invoke ``func`` while aligning keyword names with internal callers and test doubles."""

    try:
        return func(
            endpoint,
            timeout,
            allow_localhost=allow_localhost,
            allow_private=allow_private,
        )
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword argument" not in message:
            raise
        try:
            return func(
                endpoint,
                timeout,
                _allow_localhost=allow_localhost,
                _allow_private=allow_private,
            )
        except TypeError as fallback_exc:
            if "unexpected keyword argument" in str(fallback_exc):
                return func(endpoint, timeout)
            raise


def fetch_metrics(
    endpoint: str,
    timeout: float = 1.0,
    *,
    allow_localhost: bool | None = None,
    allow_private: bool | None = None,
) -> dict[str, Any] | None:
    """Return the latest metrics JSON from ``endpoint`` or ``None`` on error."""

    try:
        safe_endpoint = _validated_endpoint(
            endpoint, allow_localhost=allow_localhost, allow_private=allow_private
        )
    except ValueError:
        return None

    request = Request(safe_endpoint, headers=_build_headers("application/json"))  # noqa: S310
    result = _read_json_response(
        request,
        timeout,
        allow_localhost=allow_localhost,
        allow_private=allow_private,
    )
    if result is None:
        return None
    payload, encoding = result
    try:
        data = json.loads(payload.decode(encoding))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def fetch_history(
    endpoint: str,
    timeout: float = 1.0,
    *,
    allow_localhost: bool | None = None,
    allow_private: bool | None = None,
) -> list[dict[str, Any]] | None:
    try:
        safe_endpoint = _validated_endpoint(
            endpoint, allow_localhost=allow_localhost, allow_private=allow_private
        )
    except ValueError:
        return None

    request = Request(safe_endpoint, headers=_build_headers("application/json"))  # noqa: S310
    result = _read_json_response(
        request,
        timeout,
        allow_localhost=allow_localhost,
        allow_private=allow_private,
    )
    if result is None:
        return None
    payload, encoding = result
    try:
        data = json.loads(payload.decode(encoding))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    return None


def _build_headers(accept: str) -> dict[str, str]:
    headers = {"Accept": accept, "User-Agent": _CLIENT_USER_AGENT}
    token = os.getenv("ADHASH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _format_latency(packet: dict[str, Any]) -> str:
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


def _format_summary(tick: dict[str, Any]) -> str:
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

    def fmt(value: float | None, precision: int = 3) -> str:
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


def _format_history(history: Iterable[dict[str, Any]]) -> str:
    items = list(history)[-10:]
    if not items:
        return "History window empty — waiting for samples."

    load_series = [
        val for val in (_safe_float(item.get("load_factor")) for item in items) if val is not None
    ]
    load_line = "Load factor trend: " + (
        "  ".join(f"{val:.2f}" for val in load_series) if load_series else "n/a"
    )

    throughputs: list[float] = []
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

    class AdaptiveMetricsApp(AppBase[None]):
        """Minimal Textual application that polls and renders Adaptive Hash Map metrics."""

        latest_tick: reactive[dict[str, Any] | None] = reactive(None)
        last_updated: reactive[datetime | None] = reactive(None)

        CSS = """
        Screen { layout: vertical; }
        #status { padding: 1 2; background: #1f2937; color: #e5e7eb; }
        #summary { padding: 1 2; }
        #history { padding: 1 2; color: #94a3b8; }
        #alerts { padding: 1 2; color: #f97316; }
        """

        BINDINGS = [
            Binding("r", "refresh", "Refresh"),
            Binding("p", "reload_probe", "Reload Probe"),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(
            self,
            metrics_endpoint: str,
            history_endpoint: str | None = None,
            poll_interval: float = 2.0,
            timeout: float = 1.0,
            probe_trace: str | None = None,
            allow_localhost: bool | None = None,
            allow_private: bool | None = None,
        ) -> None:
            super().__init__()
            self.metrics_endpoint = metrics_endpoint
            self.history_endpoint = history_endpoint
            self.poll_interval = poll_interval
            self.timeout = timeout
            self._probe_path: Path | None = (
                Path(probe_trace).expanduser().resolve() if probe_trace else None
            )
            self._allow_localhost = _effective_allow_localhost(allow_localhost)
            self._allow_private = _effective_allow_private(allow_private)

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("Waiting for metrics…", id="status")
            yield Static("", id="summary")
            yield Static("", id="history")
            yield Static("", id="alerts")
            yield Static("", id="probe")
            yield Footer()

        async def on_mount(self) -> None:
            self._summary = self.query_one("#summary", Static)
            self._status = self.query_one("#status", Static)
            self._history = self.query_one("#history", Static)
            self._alerts = self.query_one("#alerts", Static)
            self._probe = self.query_one("#probe", Static)
            self.set_interval(self.poll_interval, self._poll_and_render)
            await self._poll_and_render(initial=True)
            self._render_probe_trace(initial=True)

        async def action_refresh(self) -> None:  # noqa: D401 - Textual action signature
            await self._poll_and_render()

        async def action_reload_probe(self) -> None:  # noqa: D401
            if self._probe_path is None:
                self._status.update("Set --probe-json to enable the probe visualiser.")
                return
            message = await asyncio.to_thread(self._load_probe_trace)
            self._probe.update(message)

        async def _poll_and_render(self, initial: bool = False) -> None:
            tick, history, error = await self._fetch_tick_and_history()
            now = datetime.now(tz=UTC)
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
                        "Waiting for metrics at "
                        f"{self.metrics_endpoint}. "
                        "Launch `python -m hashmap_cli` with `--metrics-port` to start streaming."
                    )

        async def _fetch_tick_and_history(
            self,
        ) -> tuple[dict[str, Any] | None, list[dict[str, Any]] | None, str | None]:
            loop = asyncio.get_running_loop()

            def _load() -> dict[str, Any] | None:
                return _call_with_network_flags(
                    fetch_metrics,
                    self.metrics_endpoint,
                    self.timeout,
                    self._allow_localhost,
                    self._allow_private,
                )

            tick = await loop.run_in_executor(None, _load)
            if tick is None:
                return None, None, None
            if tick.get("schema") not in {None, TICK_SCHEMA, SUMMARY_SCHEMA}:
                return None, None, f"Unsupported schema: {tick.get('schema')}"

            history_data: list[dict[str, Any]] | None = None
            endpoint = self.history_endpoint
            if endpoint is None and "/api/metrics" in self.metrics_endpoint:
                base = self.metrics_endpoint.rsplit("/api/metrics", 1)[0]
                endpoint = f"{base}/api/metrics/history?limit=120"
            if endpoint is not None:
                history_data = await loop.run_in_executor(
                    None,
                    lambda: _call_with_network_flags(
                        fetch_history,
                        endpoint,
                        self.timeout,
                        self._allow_localhost,
                        self._allow_private,
                    ),
                )

            return tick, history_data or [], None

        def _render_probe_trace(self, initial: bool = False) -> None:
            if not hasattr(self, "_probe"):
                return
            if self._probe_path is None:
                if initial:
                    self._probe.update(
                        "Probe visualiser inactive. Export a trace with `hashmap-cli "
                        "probe-visualize --export-json` "
                        "and launch the TUI with `--probe-json /path/to/trace.json`."
                    )
                return
            self._probe.update(self._load_probe_trace())

        def _load_probe_trace(self) -> str:
            if self._probe_path is None:
                return "Probe trace path not configured."
            try:
                data = json.loads(self._probe_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return f"Failed to load probe trace: {exc}"
            trace: dict[str, Any] | None
            seeds = None
            snapshot = None
            export_path = None
            if isinstance(data, dict) and isinstance(data.get("trace"), dict):
                trace = data["trace"]
                if isinstance(data.get("seed_entries"), list):
                    seeds = data["seed_entries"]
                if isinstance(data.get("snapshot"), str):
                    snapshot = data["snapshot"]
                if isinstance(data.get("export_json"), str):
                    export_path = data["export_json"]
            elif isinstance(data, dict):
                trace = data
            else:
                trace = None
            if trace is None:
                return 'Probe trace JSON must contain an object or {"trace": {...}}'
            lines = format_trace_lines(
                trace, snapshot=snapshot, seeds=seeds, export_path=export_path
            )
            header = f"Trace file: {self._probe_path}" if self._probe_path else ""
            return "\n".join(([header] if header else []) + lines)

else:  # pragma: no cover - exercised only when Textual is absent

    class AdaptiveMetricsApp:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise ImportError(
                "The Textual TUI requires the 'textual' extra. Install with `pip install .[ui]`."
            ) from _TEXTUAL_ERR


def run_tui(
    metrics_endpoint: str = "http://127.0.0.1:9090/api/metrics",
    history_endpoint: str | None = None,
    poll_interval: float = 2.0,
    timeout: float = 1.0,
    probe_trace: str | None = None,
    allow_localhost: bool | None = None,
    allow_private: bool | None = None,
) -> None:
    """Launch the Textual TUI against the given metrics endpoint."""

    host = urlparse(metrics_endpoint).hostname or ""
    env_local_configured = "ADHASH_ALLOW_LOCALHOST" in os.environ
    env_private_configured = "ADHASH_ALLOW_PRIVATE_IPS" in os.environ

    try:
        host_ip = ipaddress.ip_address(host)
    except ValueError:
        host_ip = None

    if allow_localhost is None and not env_local_configured and _is_local_host(host):
        allow_localhost = True

    if (
        allow_private is None
        and not env_private_configured
        and host_ip is not None
        and host_ip.is_private
    ):
        allow_private = True

    app = AdaptiveMetricsApp(
        metrics_endpoint=metrics_endpoint,
        history_endpoint=history_endpoint,
        poll_interval=poll_interval,
        timeout=timeout,
        probe_trace=probe_trace,
        allow_localhost=_effective_allow_localhost(allow_localhost),
        allow_private=_effective_allow_private(allow_private),
    )
    app.run()


__all__ = [
    "AdaptiveMetricsApp",
    "fetch_metrics",
    "run_tui",
]
