from __future__ import annotations

import gzip
import json
from collections import deque
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlparse

import pytest

from adhash.metrics import (
    ALLOW_ORIGIN,
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    CACHE_CONTROL,
    ERROR_SCHEMA,
    EVENTS_SCHEMA,
    HEALTH_SCHEMA,
    JSON_CONTENT_TYPE,
    PROMETHEUS_CONTENT_TYPE,
    SUMMARY_SCHEMA,
    TOKEN_ENV_VAR,
    VARY_HEADER,
    Metrics,
)
from adhash.metrics.server import start_metrics_server


class _DummyServer:
    """Minimal HTTPServer replacement for start_metrics_server unit tests."""

    def __init__(self, address: tuple[str, int], handler_cls: type) -> None:
        self.server_address = address
        # Ensure we behave like a bound socket by returning a non-zero port.
        self.server_port = address[1] or 4321
        self.handler_cls = handler_cls
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self) -> None:  # pragma: no cover - exercised implicitly
        return

    def shutdown(self) -> None:
        self.shutdown_called = True

    def server_close(self) -> None:
        self.closed = True


@pytest.fixture(name="handler_info")
def handler_fixture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Provide the Handler class and associated metrics without opening a socket."""

    captured: dict[str, Any] = {"handler": None, "metrics": None}

    def fake_http_server(address: tuple[str, int], handler: type) -> _DummyServer:
        captured["handler"] = handler
        return _DummyServer(address, handler)

    monkeypatch.setattr("adhash.metrics.server.HTTPServer", fake_http_server)
    metrics = Metrics()
    captured["metrics"] = metrics
    _server, stop = start_metrics_server(metrics, port=0)
    stop()
    return captured


@pytest.fixture(name="handler_with_state")
def handler_with_state_fixture(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Expose Handler while preserving the comparison payload and token."""

    captured: dict[str, Any] = {"handler": None, "metrics": None}

    def fake_http_server(address: tuple[str, int], handler: type) -> _DummyServer:
        captured["handler"] = handler
        return _DummyServer(address, handler)

    monkeypatch.setenv(TOKEN_ENV_VAR, "unit-secret")
    monkeypatch.setattr("adhash.metrics.server.HTTPServer", fake_http_server)
    metrics = Metrics()
    captured["metrics"] = metrics
    comparison_payload = {"schema": "adhash.compare.demo", "items": [{"ops": 1}]}
    _server, stop = start_metrics_server(metrics, port=0, comparison=comparison_payload)
    stop()
    assert captured["handler"] is not None
    return captured


def test_handler_seeds_token_and_comparison(handler_with_state: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_with_state["handler"])
    assert handler_cls.api_token == "unit-secret"  # noqa: S105
    assert handler_cls.comparison_payload == {
        "schema": "adhash.compare.demo",
        "items": [{"ops": 1}],
    }
    assert handler_cls.server_version == "AdaptiveHashMap"
    assert handler_cls.sys_version == ""


def test_common_headers_use_canonical_names(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    calls: list[tuple[str, str]] = []

    class FakeResponse:
        command = "GET"

        def send_header(self, name: str, value: str) -> None:
            calls.append((name, value))

    handler_cls._set_common_headers(
        FakeResponse(), content_type="application/json", length=42, gzip_enabled=True
    )
    expected_pairs = [
        ("Content-Type", "application/json"),
        ("Content-Length", "42"),
        ("Cache-Control", CACHE_CONTROL),
        ("Access-Control-Allow-Origin", ALLOW_ORIGIN),
        ("Access-Control-Allow-Methods", ALLOWED_METHODS),
        ("Access-Control-Allow-Headers", ALLOWED_HEADERS),
        ("Vary", VARY_HEADER),
        ("Content-Encoding", "gzip"),
    ]
    assert calls == expected_pairs

    gzip_calls: list[tuple[str, str]] = []
    handler_cls._set_common_headers(
        SimpleNamespace(
            send_header=lambda name, value: gzip_calls.append((name, value)), command="GET"
        ),
        content_type="text/plain",
        length=5,
        gzip_enabled=False,
    )
    expected_pairs_no_gzip = [
        ("Content-Type", "text/plain"),
        ("Content-Length", "5"),
        ("Cache-Control", CACHE_CONTROL),
        ("Access-Control-Allow-Origin", ALLOW_ORIGIN),
        ("Access-Control-Allow-Methods", ALLOWED_METHODS),
        ("Access-Control-Allow-Headers", ALLOWED_HEADERS),
        ("Vary", VARY_HEADER),
    ]
    assert gzip_calls == expected_pairs_no_gzip

    default_calls: list[tuple[str, str]] = []
    handler_cls._set_common_headers(
        SimpleNamespace(
            send_header=lambda name, value: default_calls.append((name, value)), command="GET"
        ),
        content_type="text/html",
        length=3,
    )
    assert default_calls == [
        ("Content-Type", "text/html"),
        ("Content-Length", "3"),
        ("Cache-Control", CACHE_CONTROL),
        ("Access-Control-Allow-Origin", ALLOW_ORIGIN),
        ("Access-Control-Allow-Methods", ALLOWED_METHODS),
        ("Access-Control-Allow-Headers", ALLOWED_HEADERS),
        ("Vary", VARY_HEADER),
    ]
    assert all(name.lower() != "content-encoding" for name, _ in gzip_calls)


def test_unauthorized_payload_is_structured(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    captured: dict[str, Any] = {}

    class FakeHandler:
        command = "GET"

        def _write_json(self, payload: Any, status: int = 200) -> None:
            captured["payload"] = payload
            captured["status"] = status

        def _limit(self, parsed: Any, default: int, *, clamp: int | None = None) -> int:
            return int(handler_cls._limit(self, parsed, default, clamp=clamp))

    handler_cls._unauthorized(FakeHandler())
    payload = captured["payload"]
    assert captured["status"] == 401
    assert payload["schema"] == ERROR_SCHEMA
    assert payload["error"] == "unauthorized"
    assert "generated_at" in payload


def test_authorized_defaults_to_header_token(handler_with_state: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_with_state["handler"])

    class FakeHandler:
        command = "GET"
        headers = {"Authorization": "Bearer unit-secret"}
        path = "/"

    assert handler_cls._authorized(FakeHandler()) is True
    no_header = SimpleNamespace(command="GET", headers={}, path="/")
    assert handler_cls._authorized(no_header) is False


def test_write_json_passes_through_common_headers(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    captured: dict[str, Any] = {}

    class FakeHandler:
        command = "GET"
        headers: dict[str, str] = {}

        def _write_body(
            self,
            body: bytes,
            content_type: str,
            *,
            gzip_enabled: bool = False,
            status: int = 200,
        ) -> None:
            captured["body"] = body
            captured["content_type"] = content_type
            captured["gzip_enabled"] = gzip_enabled
            captured["status"] = status

        def _client_supports_gzip(self) -> bool:
            return False

    handler_cls._write_json(FakeHandler(), {"schema": SUMMARY_SCHEMA}, status=202)
    assert captured["status"] == 202
    assert captured["content_type"] == JSON_CONTENT_TYPE
    assert captured["gzip_enabled"] is False
    assert json.loads(captured["body"].decode("utf-8"))["schema"] == SUMMARY_SCHEMA

    gzip_captured: dict[str, Any] = {}

    class FakeGzipHandler(FakeHandler):
        headers = {"Accept-Encoding": "gzip"}

        def _client_supports_gzip(self) -> bool:
            return True

        def _write_body(
            self,
            body: bytes,
            content_type: str,
            *,
            gzip_enabled: bool = False,
            status: int = 200,
        ) -> None:
            gzip_captured["body"] = body
            gzip_captured["content_type"] = content_type
            gzip_captured["gzip_enabled"] = gzip_enabled
            gzip_captured["status"] = status

    handler_cls._write_json(FakeGzipHandler(), {"schema": SUMMARY_SCHEMA})
    assert gzip_captured["status"] == 200
    assert gzip_captured["gzip_enabled"] is True
    assert gzip_captured["content_type"] == JSON_CONTENT_TYPE
    assert (
        json.loads(gzip.decompress(gzip_captured["body"]).decode("utf-8"))["schema"]
        == SUMMARY_SCHEMA
    )


def test_write_body_respects_defaults_and_writes_payload(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])

    class FakeHandler:
        def __init__(self) -> None:
            self.command = "GET"
            self.sent_status: list[int] = []
            self.header_args: list[dict[str, Any]] = []
            self.end_calls = 0
            self.written: list[bytes] = []

        def send_response(self, status: int) -> None:
            self.sent_status.append(status)

        def _set_common_headers(
            self, *, content_type: str, length: int, gzip_enabled: bool = False
        ) -> None:
            self.header_args.append(
                {
                    "content_type": content_type,
                    "length": length,
                    "gzip": gzip_enabled,
                }
            )

        def end_headers(self) -> None:
            self.end_calls += 1

        def wfile_write(self, body: bytes) -> None:
            self.written.append(body)

        @property
        def wfile(self) -> SimpleNamespace:
            return SimpleNamespace(write=self.wfile_write)

    fake = FakeHandler()
    handler_cls._write_body(fake, b"abc", "application/json")
    assert fake.sent_status == [200]
    assert fake.header_args == [{"content_type": "application/json", "length": 3, "gzip": False}]
    assert fake.end_calls == 1
    assert fake.written == [b"abc"]

    fake.command = "HEAD"
    handler_cls._write_body(fake, b"xyz", "text/plain", gzip_enabled=True, status=204)
    assert fake.sent_status[-1] == 204
    assert fake.header_args[-1] == {"content_type": "text/plain", "length": 3, "gzip": True}
    assert fake.written == [b"abc"]


def test_events_payload_schema(handler_with_state: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_with_state["handler"])
    metrics_any = cast(Any, handler_with_state["metrics"])
    metrics_any.events_history = deque([{"idx": 1}, {"idx": 2}])
    captured: dict[str, Any] = {}

    class FakeHandler:
        command = "GET"

        def _write_json(self, payload: Any, status: int = 200) -> None:
            captured["payload"] = payload
            captured["status"] = status

        def _limit(
            self, _parsed: Any, _default: int, *, clamp: int | None = None
        ) -> int:  # noqa: ARG002
            del clamp
            return 1

    handler_cls._serve_events(FakeHandler(), SimpleNamespace())
    payload = captured["payload"]
    assert payload["schema"] == EVENTS_SCHEMA
    assert payload["events"][0] == {"idx": 2}


def test_events_endpoint_handles_missing_history(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    if hasattr(metrics_any, "events_history"):
        delattr(metrics_any, "events_history")
    captured: dict[str, Any] = {}

    class FakeHandler:
        command = "GET"

        def _write_json(self, payload: Any, status: int = 200) -> None:
            captured["payload"] = payload
            captured["status"] = status

        def _limit(self, parsed: Any, default: int, *, clamp: int | None = None) -> int:
            return int(handler_cls._limit(self, parsed, default, clamp=clamp))

    handler_cls._serve_events(FakeHandler(), urlparse("/api/events?limit=5"))
    payload = captured["payload"]
    assert captured["status"] == 200
    assert payload["schema"] == EVENTS_SCHEMA
    assert payload["events"] == []

    metrics_any.events_history = None
    captured.clear()
    handler_cls._serve_events(FakeHandler(), urlparse("/api/events?limit=5"))
    assert captured["payload"]["events"] == []

    metrics_any.events_history = deque([{"idx": 10}, {"idx": 11}])
    captured.clear()
    handler_cls._serve_events(FakeHandler(), urlparse("/api/events?limit=1"))
    assert captured["payload"]["events"] == [{"idx": 11}]

    metrics_any.events_history = object()
    captured.clear()
    handler_cls._serve_events(FakeHandler(), urlparse("/api/events?limit=3"))
    assert captured["payload"]["events"] == []


def test_client_supports_gzip_parses_accept_encoding(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    assert (
        handler_cls._client_supports_gzip(
            SimpleNamespace(headers={"Accept-Encoding": "gzip, deflate"})
        )
        is True
    )
    assert (
        handler_cls._client_supports_gzip(SimpleNamespace(headers={"Accept-Encoding": ";, gzip"}))
        is True
    )
    assert (
        handler_cls._client_supports_gzip(SimpleNamespace(headers={"Accept-Encoding": "gzip;q=1"}))
        is True
    )
    assert (
        handler_cls._client_supports_gzip(SimpleNamespace(headers={"Accept-Encoding": "gzip;q=0"}))
        is False
    )
    assert (
        handler_cls._client_supports_gzip(
            SimpleNamespace(headers={"Accept-Encoding": "br, gzip; q=0.4"})
        )
        is True
    )
    assert (
        handler_cls._client_supports_gzip(SimpleNamespace(headers={"Accept-Encoding": " , , gzip"}))
        is True
    )
    assert (
        handler_cls._client_supports_gzip(
            SimpleNamespace(headers={"Accept-Encoding": "gzip;q=foo"})
        )
        is False
    )
    assert handler_cls._client_supports_gzip(SimpleNamespace(headers={})) is False


def test_authorized_allows_missing_token(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    fake = SimpleNamespace(headers={}, path="/", command="GET")
    assert handler_cls._authorized(fake) is True


def test_authorized_accepts_header_and_query(handler_with_state: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_with_state["handler"])
    header_request = SimpleNamespace(
        headers={"Authorization": "Bearer unit-secret"}, path="/", command="GET"
    )
    assert handler_cls._authorized(header_request) is True

    query_request = SimpleNamespace(headers={}, path="/dashboard?token=unit-secret", command="GET")
    assert handler_cls._authorized(query_request) is True

    mismatch_request = SimpleNamespace(headers={}, path="/?token=wrong", command="GET")
    assert handler_cls._authorized(mismatch_request) is False


def test_limit_parses_query_and_clamps(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    dummy = SimpleNamespace()
    assert handler_cls._limit(dummy, urlparse("/path?limit=10"), default=5, clamp=20) == 10
    assert handler_cls._limit(dummy, urlparse("/path?limit=0"), default=5, clamp=20) == 1
    assert handler_cls._limit(dummy, urlparse("/path?limit=999"), default=5, clamp=20) == 20
    assert handler_cls._limit(dummy, urlparse("/path"), default=7, clamp=20) == 7
    assert handler_cls._limit(dummy, urlparse("/path?limit=abc"), default=9, clamp=None) == 9


def test_history_rows_prefers_buffer_and_falls_back(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    metrics_any.history_buffer = deque(maxlen=4)
    metrics_any.history_buffer.extend([{"idx": 0}, {"idx": 1}, {"idx": 2}])
    rows = handler_cls._history_rows(SimpleNamespace(), 2)
    assert rows == [{"idx": 1}, {"idx": 2}]

    metrics_any.history_buffer = None
    metrics_any.latest_tick = {"idx": 99}
    assert handler_cls._history_rows(SimpleNamespace(), 5) == [{"idx": 99}]


def test_history_rows_handles_missing_attributes(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    if hasattr(metrics_any, "history_buffer"):
        delattr(metrics_any, "history_buffer")
    if hasattr(metrics_any, "latest_tick"):
        delattr(metrics_any, "latest_tick")
    assert handler_cls._history_rows(SimpleNamespace(), 3) == []
    metrics_any.latest_tick = {"idx": 77}
    assert handler_cls._history_rows(SimpleNamespace(), 1) == [{"idx": 77}]
    metrics_any.history_buffer = None
    metrics_any.latest_tick = None


def test_serve_health_emits_schema_payload(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    captured: dict[str, Any] = {}

    class FakeHandler:
        command = "GET"

        def _write_json(self, payload: Any, status: int = 200) -> None:
            captured["payload"] = payload
            captured["status"] = status

    handler_cls._serve_health(FakeHandler())
    payload = captured["payload"]
    assert captured["status"] == 200
    assert payload["schema"] == HEALTH_SCHEMA
    assert payload["status"] == "ok"
    assert isinstance(payload["generated_at"], float)


def test_serve_metrics_prometheus_encodes_output(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    metrics_any.render = lambda: "# HELP test 1"
    captured: dict[str, Any] = {}

    class FakeHandler:
        command = "GET"

        def _write_body(
            self,
            body: bytes,
            content_type: str,
            *,
            gzip_enabled: bool = False,
            status: int = 200,
        ) -> None:
            captured["body"] = body
            captured["content_type"] = content_type
            captured["gzip_enabled"] = gzip_enabled
            captured["status"] = status

    handler_cls._serve_metrics_prometheus(FakeHandler())
    assert captured["content_type"] == PROMETHEUS_CONTENT_TYPE
    assert captured["status"] == 200
    assert captured["gzip_enabled"] is False
    assert captured["body"] == b"# HELP test 1"


def test_serve_metrics_summary_includes_history(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    metrics_any.history_buffer = deque([{"idx": 1}, {"idx": 2}, {"idx": 3}])
    original_builder = metrics_any.build_summary_payload
    metrics_any.build_summary_payload = lambda: {"schema": SUMMARY_SCHEMA, "items": []}
    captured: dict[str, Any] = {}

    def invoke(parsed: Any | None) -> dict[str, Any]:
        def _write_json(_self: Any, payload: Any, status: int = 200) -> None:
            captured["payload"] = payload
            captured["status"] = status

        def _limit(self: Any, parsed_obj: Any, default: int, *, clamp: int | None = None) -> int:
            return int(handler_cls._limit(self, parsed_obj, default, clamp=clamp))

        def _history_rows(self: Any, limit: int) -> Any:
            return handler_cls._history_rows(self, limit)

        fake_handler_cls = type(
            "FakeHandler",
            (),
            {
                "command": "GET",
                "_write_json": _write_json,
                "_limit": _limit,
                "_history_rows": _history_rows,
            },
        )

        handler_cls._serve_metrics_summary(fake_handler_cls(), parsed)
        return captured

    parsed = urlparse("/api/metrics?limit=2")
    invoke(parsed)
    payload = captured["payload"]
    assert captured["status"] == 200
    assert payload["schema"] == SUMMARY_SCHEMA
    assert payload["items"] == [{"idx": 2}, {"idx": 3}]
    metrics_any.build_summary_payload = original_builder
    metrics_any.history_buffer = None


def test_serve_metrics_summary_defaults_to_single_item(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    metrics_any.history_buffer = deque([{"idx": 1}, {"idx": 2}])
    original_builder = metrics_any.build_summary_payload
    metrics_any.build_summary_payload = lambda: {"schema": SUMMARY_SCHEMA, "items": []}
    captured: dict[str, Any] = {}

    def _write_json(_self: Any, payload: Any, status: int = 200) -> None:
        captured["payload"] = payload
        captured["status"] = status

    handler = type(
        "SummaryHandler",
        (),
        {
            "command": "GET",
            "_write_json": _write_json,
            "_limit": lambda self, parsed_obj, default, *, clamp=None: int(
                handler_cls._limit(self, parsed_obj, default, clamp=clamp)
            ),
            "_history_rows": lambda self, limit: handler_cls._history_rows(self, limit),
        },
    )()

    handler_cls._serve_metrics_summary(handler, None)
    payload = captured["payload"]
    assert payload["items"] == [{"idx": 2}]
    metrics_any.build_summary_payload = original_builder
    metrics_any.history_buffer = None


def test_serve_metrics_summary_handles_invalid_limit(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    metrics_any.history_buffer = deque([{"idx": 1}, {"idx": 2}, {"idx": 3}])
    original_builder = metrics_any.build_summary_payload
    metrics_any.build_summary_payload = lambda: {"schema": SUMMARY_SCHEMA, "items": []}
    captured: dict[str, Any] = {}

    def _write_json(_self: Any, payload: Any, status: int = 200) -> None:
        captured["payload"] = payload
        captured["status"] = status

    handler = type(
        "SummaryHandlerInvalid",
        (),
        {
            "command": "GET",
            "_write_json": _write_json,
            "_limit": lambda self, parsed_obj, default, *, clamp=None: int(
                handler_cls._limit(self, parsed_obj, default, clamp=clamp)
            ),
            "_history_rows": lambda self, limit: handler_cls._history_rows(self, limit),
        },
    )()

    handler_cls._serve_metrics_summary(handler, urlparse("/api/metrics?limit=abc"))
    payload = captured["payload"]
    assert payload["items"] == [{"idx": 3}]
    metrics_any.build_summary_payload = original_builder
    metrics_any.history_buffer = None


def test_serve_metrics_summary_falls_back_to_latest_tick(handler_info: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_info["handler"])
    metrics_any = cast(Any, handler_info["metrics"])
    metrics_any.history_buffer = deque([], maxlen=4)
    metrics_any.latest_tick = {"idx": 42}
    original_builder = metrics_any.build_summary_payload
    metrics_any.build_summary_payload = lambda: {"schema": SUMMARY_SCHEMA, "items": []}
    captured: dict[str, Any] = {}

    def _write_json(_self: Any, payload: Any, status: int = 200) -> None:
        captured["payload"] = payload
        captured["status"] = status

    handler = type(
        "SummaryHandlerFallback",
        (),
        {
            "command": "GET",
            "_write_json": _write_json,
            "_limit": lambda self, parsed_obj, default, *, clamp=None: int(
                handler_cls._limit(self, parsed_obj, default, clamp=clamp)
            ),
            "_history_rows": lambda self, limit: handler_cls._history_rows(self, limit),
        },
    )()

    handler_cls._serve_metrics_summary(handler, None)
    payload = captured.get("payload")
    assert payload is not None
    assert payload["items"] == [{"idx": 42}]
    metrics_any.build_summary_payload = original_builder
    metrics_any.history_buffer = None
    metrics_any.latest_tick = None


def test_serve_comparison_returns_payload_or_404(handler_with_state: dict[str, Any]) -> None:
    handler_cls = cast(Any, handler_with_state["handler"])
    captured: dict[str, Any] = {}

    def _write_json(_self: Any, payload: Any, status: int = 200) -> None:
        captured.setdefault("calls", []).append((payload, status))

    handler = type(
        "ComparisonHandler",
        (),
        {
            "command": "GET",
            "_write_json": _write_json,
        },
    )()

    handler_cls._serve_comparison(handler)
    payload, status = captured["calls"][0]
    assert status == 200
    assert payload == handler_cls.comparison_payload

    original_payload = handler_cls.comparison_payload
    handler_cls.comparison_payload = None
    handler_cls._serve_comparison(handler)
    payload, status = captured["calls"][1]
    assert status == 404
    assert payload["detail"] == "comparison data not loaded"
    assert payload["schema"] == "adhash.compare.none"
    handler_cls.comparison_payload = original_payload
