from __future__ import annotations

import pytest

from adhash.tui import app as tui_app


def test_is_local_host_detects_loopback_and_unspecified() -> None:
    assert tui_app._is_local_host("127.0.0.1")
    assert tui_app._is_local_host("::1")
    assert tui_app._is_local_host("0.0.0.0")  # noqa: S104
    assert not tui_app._is_local_host("example.com")


def test_validated_endpoint_blocks_file_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADHASH_ALLOW_LOCALHOST", raising=False)
    monkeypatch.delenv("ADHASH_ALLOW_PRIVATE_IPS", raising=False)
    with pytest.raises(ValueError):
        tui_app._validated_endpoint("file:///etc/passwd")


def test_validated_endpoint_requires_localhost_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADHASH_ALLOW_LOCALHOST", raising=False)
    monkeypatch.delenv("ADHASH_ALLOW_PRIVATE_IPS", raising=False)
    with pytest.raises(ValueError):
        tui_app._validated_endpoint("http://127.0.0.1:9090/api/metrics", allow_localhost=False)


def test_validated_endpoint_allows_localhost_when_opted_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ADHASH_ALLOW_LOCALHOST", raising=False)
    monkeypatch.delenv("ADHASH_ALLOW_PRIVATE_IPS", raising=False)
    endpoint = tui_app._validated_endpoint(
        "http://127.0.0.1:9090/api/metrics", allow_localhost=True
    )
    assert endpoint.endswith("/api/metrics")
