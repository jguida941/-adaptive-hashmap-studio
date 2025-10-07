import io
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from adhash.config import WatchdogPolicy
from adhash.metrics.core import (
    Metrics,
    ThresholdWatchdog,
    apply_tick_to_metrics,
    format_bucket_label,
    parse_tick_line,
    resolve_ema_alpha,
    stream_metrics_file,
)


def _make_tick() -> Dict[str, Any]:
    return {
        "schema": "tick.v1",
        "ops": 10,
        "ops_by_type": {"put": 4, "get": 5, "del": 1},
        "migrations": 2,
        "compactions": 1,
        "load_factor": 0.75,
        "max_group_len": 3,
        "avg_probe_estimate": 5.5,
        "tombstone_ratio": 0.12,
        "backend": "robinhood",
        "latency_ms": {
            "overall": {"p50": 1.0, "p90": 2.0, "p99": 3.0},
            "get": {"p50": 0.5, "p90": 0.75, "p99": 1.0},
        },
        "latency_summary_stats": {"overall": {"count": 5, "sum": 10.0}},
        "latency_histograms": {
            "overall": [
                {"le": 1.0, "count": 3},
                {"le": math.inf, "count": 5},
            ]
        },
        "probe_hist": [[1, 2], [2, 1]],
        "alerts": [{"metric": "load_factor", "value": 0.75}],
        "alert_flags": {"load_factor": True},
        "key_heatmap": {"rows": 1, "cols": 1, "matrix": [[1]], "max": 1, "total": 1, "slot_span": 1, "original_slots": 1},
        "events": [{"type": "info", "message": "tick"}],
        "t": time.time(),
    }


def test_resolve_ema_alpha_clamps_values(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ADHASH_OPS_ALPHA", "1.5")
    assert resolve_ema_alpha(default=0.2) == 1.0
    monkeypatch.setenv("ADHASH_OPS_ALPHA", "-4")
    assert resolve_ema_alpha(default=0.2) == 0.0
    monkeypatch.setenv("ADHASH_OPS_ALPHA", "invalid")
    assert resolve_ema_alpha(default=0.3) == 0.3


def test_apply_tick_updates_metrics_and_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    metrics = Metrics()
    metrics.history_buffer = []
    first_tick = _make_tick()
    apply_tick_to_metrics(metrics, first_tick)

    # Second tick exercises EMA averaging path
    second_tick = _make_tick()
    second_tick["ops"] = 30
    second_tick["ops_per_second"] = 20.0
    apply_tick_to_metrics(metrics, second_tick)

    rendered = metrics.render()
    assert "hashmap_ops_total 30" in rendered
    assert 'hashmap_backend_info{name="robinhood"} 1' in rendered
    assert 'hashmap_latency_ms_hist_bucket{op="overall",le="+Inf"} 5' in rendered

    payload = metrics.build_summary_payload()
    assert payload["totals"]["puts"] == 4
    assert payload["backend_state"]["avg_probe_estimate"] == 5.5
    assert payload["alert_flags"]["load_factor"] is True
    assert metrics.events_history, "events should be captured"

    # ensure history buffer appended copies
    assert metrics.history_buffer and isinstance(metrics.history_buffer[0], dict)


def test_format_bucket_label_handles_infinity():
    assert format_bucket_label(math.inf) == "+Inf"
    assert format_bucket_label(1.23456789) == "1.234568"


def test_parse_tick_line_filters_invalid_entries(caplog: pytest.LogCaptureFixture):
    assert parse_tick_line("not-json") is None
    assert parse_tick_line(json.dumps([])) is None
    assert parse_tick_line(json.dumps({"schema": "unknown"})) is None
    from adhash.metrics.constants import TICK_SCHEMA

    valid = parse_tick_line(json.dumps({"schema": TICK_SCHEMA, "ops": 1}))
    assert valid == {"schema": TICK_SCHEMA, "ops": 1}


def test_stream_metrics_file_handles_missing_path(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    missing = tmp_path / "missing.ndjson"
    calls: List[Dict[str, Any]] = []
    stream_metrics_file(missing, follow=False, callback=calls.append, poll_interval=0.01)
    assert not calls


def test_threshold_watchdog_emits_alerts_and_resets(caplog: pytest.LogCaptureFixture):
    caplog.set_level("INFO", logger="hashmap_cli")
    policy = WatchdogPolicy(enabled=True, load_factor_warn=0.5, avg_probe_warn=1.0, tombstone_ratio_warn=None)
    watchdog = ThresholdWatchdog(policy)

    tick = {"backend": "adaptive", "load_factor": 0.75, "avg_probe_estimate": 2.0, "tombstone_ratio": 0.1}
    alerts, flags = watchdog.evaluate(tick)
    assert len(alerts) == 2
    assert flags["load_factor"] is True
    assert flags["avg_probe_estimate"] is True

    tick_low = {"backend": "adaptive", "load_factor": 0.4, "avg_probe_estimate": 0.5}
    alerts, flags = watchdog.evaluate(tick_low)
    assert not alerts
    assert flags["load_factor"] is False
    assert flags["avg_probe_estimate"] is False

    policy.enabled = False
    alerts, flags = watchdog.evaluate(tick)
    assert not alerts and not flags
