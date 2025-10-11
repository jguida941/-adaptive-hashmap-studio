import json
import math
import time
from collections import deque
from pathlib import Path
from typing import Any

import pytest

from adhash.config import WatchdogPolicy
from adhash.metrics.core import (
    Metrics,
    ThresholdWatchdog,
    _coerce_alert_flag,
    apply_tick_to_metrics,
    format_bucket_label,
    parse_tick_line,
    resolve_ema_alpha,
    stream_metrics_file,
)


def test_metrics_initial_state_defaults() -> None:
    metrics = Metrics()
    assert metrics.ops_total == 0
    assert metrics.puts_total == 0
    assert metrics.gets_total == 0
    assert metrics.dels_total == 0
    assert metrics.migrations_total == 0
    assert metrics.compactions_total == 0
    assert metrics.load_factor == 0.0
    assert metrics.max_group_len == 0.0
    assert metrics.avg_probe_estimate == 0.0
    assert metrics.backend_name == "unknown"
    assert metrics.latest_tick is None
    assert metrics.tombstone_ratio == 0.0
    assert metrics.alert_flags == {}
    assert metrics.active_alerts == []
    assert metrics.latency_summary_stats == {}
    assert metrics.latency_histograms == {}
    assert metrics.history_buffer is None
    assert isinstance(metrics.events_history, deque)
    assert metrics.events_history.maxlen == 512
    assert metrics.key_heatmap == {
        "rows": 0,
        "cols": 0,
        "matrix": [],
        "max": 0,
        "total": 0,
        "slot_span": 1,
        "original_slots": 0,
    }
    assert metrics._ema_ops == 0.0
    assert metrics._ops_prev is None
    assert metrics._t_prev is None
    assert metrics._last_instant is None


def _make_tick() -> dict[str, Any]:
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
        "key_heatmap": {
            "rows": 1,
            "cols": 1,
            "matrix": [[1]],
            "max": 1,
            "total": 1,
            "slot_span": 1,
            "original_slots": 1,
        },
        "events": [{"type": "info", "message": "tick"}],
        "t": time.time(),
    }


def test_resolve_ema_alpha_clamps_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_OPS_ALPHA", "1.5")
    assert resolve_ema_alpha(default=0.2) == 1.0
    monkeypatch.setenv("ADHASH_OPS_ALPHA", "-4")
    assert resolve_ema_alpha(default=0.2) == 0.0
    monkeypatch.setenv("ADHASH_OPS_ALPHA", "invalid")
    assert resolve_ema_alpha(default=0.3) == 0.3


def test_resolve_ema_alpha_defaults_and_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADHASH_OPS_ALPHA", raising=False)
    assert resolve_ema_alpha() == 0.25
    monkeypatch.setenv("ADHASH_OPS_ALPHA", " 0.6 ")
    assert resolve_ema_alpha(default=0.1) == 0.6


def test_apply_tick_updates_metrics_and_render(_monkeypatch: pytest.MonkeyPatch) -> None:
    metrics = Metrics()
    metrics.history_buffer = deque()
    first_tick = _make_tick()
    apply_tick_to_metrics(metrics, first_tick)

    # Second tick exercises EMA averaging path
    second_tick = _make_tick()
    second_tick["ops"] = 30
    second_tick["ops_per_second"] = 20.0
    apply_tick_to_metrics(metrics, second_tick)

    rendered = metrics.render()
    assert rendered.splitlines()[0] == "# HELP hashmap_ops_total Total operations processed"
    assert "# TYPE hashmap_load_factor gauge" in rendered
    assert "hashmap_ops_total 30" in rendered
    assert 'hashmap_backend_info{name="robinhood"} 1' in rendered
    assert (
        "# HELP hashmap_latency_ms Latency percentiles (ms) by operation and quantile" in rendered
    )
    assert "# HELP hashmap_latency_ms_hist Sampled latency histogram (ms) per operation" in rendered
    assert 'hashmap_latency_ms_hist_bucket{op="overall",le="+Inf"} 5' in rendered
    assert (
        "# HELP hashmap_probe_length_count Probe length histogram (count per distance)" in rendered
    )
    assert "# HELP hashmap_watchdog_alert_active Guardrail alert state (1=active)" in rendered
    lines = rendered.splitlines()
    expected_prefix = [
        "# HELP hashmap_ops_total Total operations processed",
        "# TYPE hashmap_ops_total counter",
        "hashmap_ops_total 30",
        "# HELP hashmap_puts_total Total put operations",
        "# TYPE hashmap_puts_total counter",
        "hashmap_puts_total 4",
        "# HELP hashmap_gets_total Total get operations",
        "# TYPE hashmap_gets_total counter",
        "hashmap_gets_total 5",
        "# HELP hashmap_dels_total Total delete operations",
        "# TYPE hashmap_dels_total counter",
        "hashmap_dels_total 1",
        "# HELP hashmap_migrations_total Backend migrations",
        "# TYPE hashmap_migrations_total counter",
        "hashmap_migrations_total 2",
        "# HELP hashmap_compactions_total Backend compactions",
        "# TYPE hashmap_compactions_total counter",
        "hashmap_compactions_total 1",
        "# HELP hashmap_load_factor Current load factor",
        "# TYPE hashmap_load_factor gauge",
        "hashmap_load_factor 0.750000",
        "# HELP hashmap_max_group_len Max inner group length (chaining)",
        "# TYPE hashmap_max_group_len gauge",
        "hashmap_max_group_len 3.000000",
        "# HELP hashmap_avg_probe_estimate Estimated avg probe distance (robinhood)",
        "# TYPE hashmap_avg_probe_estimate gauge",
        "hashmap_avg_probe_estimate 5.500000",
        "# HELP hashmap_tombstone_ratio Tombstone ratio for RobinHood backend",
        "# TYPE hashmap_tombstone_ratio gauge",
        "hashmap_tombstone_ratio 0.120000",
        "# HELP hashmap_backend_info Backend in use (label)",
        "# TYPE hashmap_backend_info gauge",
        'hashmap_backend_info{name="robinhood"} 1',
        "# HELP hashmap_latency_ms Latency percentiles (ms) by operation and quantile",
        "# TYPE hashmap_latency_ms gauge",
        'hashmap_latency_ms{op="overall",quantile="p50"} 1.000000',
        'hashmap_latency_ms{op="overall",quantile="p90"} 2.000000',
        'hashmap_latency_ms{op="overall",quantile="p99"} 3.000000',
        'hashmap_latency_ms{op="get",quantile="p50"} 0.500000',
        'hashmap_latency_ms{op="get",quantile="p90"} 0.750000',
        'hashmap_latency_ms{op="get",quantile="p99"} 1.000000',
        "# HELP hashmap_latency_ms_summary Sampled latency summaries (ms) per operation",
        "# TYPE hashmap_latency_ms_summary summary",
        'hashmap_latency_ms_summary{op="overall",quantile="0.5"} 1.000000',
        'hashmap_latency_ms_summary{op="overall",quantile="0.9"} 2.000000',
        'hashmap_latency_ms_summary{op="overall",quantile="0.99"} 3.000000',
        'hashmap_latency_ms_summary_sum{op="overall"} 10.000000',
        'hashmap_latency_ms_summary_count{op="overall"} 5',
        "# HELP hashmap_latency_ms_hist Sampled latency histogram (ms) per operation",
        "# TYPE hashmap_latency_ms_hist histogram",
        'hashmap_latency_ms_hist_bucket{op="overall",le="1.000000"} 3',
        'hashmap_latency_ms_hist_bucket{op="overall",le="+Inf"} 5',
        'hashmap_latency_ms_hist_sum{op="overall"} 10.000000',
        'hashmap_latency_ms_hist_count{op="overall"} 5',
        "# HELP hashmap_probe_length_count Probe length histogram (count per distance)",
        "# TYPE hashmap_probe_length_count gauge",
        'hashmap_probe_length_count{distance="1"} 2',
        'hashmap_probe_length_count{distance="2"} 1',
        "# HELP hashmap_watchdog_alert_active Guardrail alert state (1=active)",
        "# TYPE hashmap_watchdog_alert_active gauge",
        'hashmap_watchdog_alert_active{metric="load_factor"} 1',
    ]
    for idx, expected_line in enumerate(expected_prefix):
        assert lines[idx] == expected_line
    expected_render = """# HELP hashmap_ops_total Total operations processed
# TYPE hashmap_ops_total counter
hashmap_ops_total 30
# HELP hashmap_puts_total Total put operations
# TYPE hashmap_puts_total counter
hashmap_puts_total 4
# HELP hashmap_gets_total Total get operations
# TYPE hashmap_gets_total counter
hashmap_gets_total 5
# HELP hashmap_dels_total Total delete operations
# TYPE hashmap_dels_total counter
hashmap_dels_total 1
# HELP hashmap_migrations_total Backend migrations
# TYPE hashmap_migrations_total counter
hashmap_migrations_total 2
# HELP hashmap_compactions_total Backend compactions
# TYPE hashmap_compactions_total counter
hashmap_compactions_total 1
# HELP hashmap_load_factor Current load factor
# TYPE hashmap_load_factor gauge
hashmap_load_factor 0.750000
# HELP hashmap_max_group_len Max inner group length (chaining)
# TYPE hashmap_max_group_len gauge
hashmap_max_group_len 3.000000
# HELP hashmap_avg_probe_estimate Estimated avg probe distance (robinhood)
# TYPE hashmap_avg_probe_estimate gauge
hashmap_avg_probe_estimate 5.500000
# HELP hashmap_tombstone_ratio Tombstone ratio for RobinHood backend
# TYPE hashmap_tombstone_ratio gauge
hashmap_tombstone_ratio 0.120000
# HELP hashmap_backend_info Backend in use (label)
# TYPE hashmap_backend_info gauge
hashmap_backend_info{name=\"robinhood\"} 1
# HELP hashmap_latency_ms Latency percentiles (ms) by operation and quantile
# TYPE hashmap_latency_ms gauge
hashmap_latency_ms{op=\"overall\",quantile=\"p50\"} 1.000000
hashmap_latency_ms{op=\"overall\",quantile=\"p90\"} 2.000000
hashmap_latency_ms{op=\"overall\",quantile=\"p99\"} 3.000000
hashmap_latency_ms{op=\"get\",quantile=\"p50\"} 0.500000
hashmap_latency_ms{op=\"get\",quantile=\"p90\"} 0.750000
hashmap_latency_ms{op=\"get\",quantile=\"p99\"} 1.000000
# HELP hashmap_latency_ms_summary Sampled latency summaries (ms) per operation
# TYPE hashmap_latency_ms_summary summary
hashmap_latency_ms_summary{op=\"overall\",quantile=\"0.5\"} 1.000000
hashmap_latency_ms_summary{op=\"overall\",quantile=\"0.9\"} 2.000000
hashmap_latency_ms_summary{op=\"overall\",quantile=\"0.99\"} 3.000000
hashmap_latency_ms_summary_sum{op=\"overall\"} 10.000000
hashmap_latency_ms_summary_count{op=\"overall\"} 5
# HELP hashmap_latency_ms_hist Sampled latency histogram (ms) per operation
# TYPE hashmap_latency_ms_hist histogram
hashmap_latency_ms_hist_bucket{op=\"overall\",le=\"1.000000\"} 3
hashmap_latency_ms_hist_bucket{op=\"overall\",le=\"+Inf\"} 5
hashmap_latency_ms_hist_sum{op=\"overall\"} 10.000000
hashmap_latency_ms_hist_count{op=\"overall\"} 5
# HELP hashmap_probe_length_count Probe length histogram (count per distance)
# TYPE hashmap_probe_length_count gauge
hashmap_probe_length_count{distance=\"1\"} 2
hashmap_probe_length_count{distance=\"2\"} 1
# HELP hashmap_watchdog_alert_active Guardrail alert state (1=active)
# TYPE hashmap_watchdog_alert_active gauge
hashmap_watchdog_alert_active{metric=\"load_factor\"} 1
"""
    assert rendered == expected_render

    payload = metrics.build_summary_payload()
    assert payload["totals"]["puts"] == 4
    assert payload["backend_state"]["avg_probe_estimate"] == 5.5
    assert payload["alert_flags"]["load_factor"] is True
    assert metrics.events_history, "events should be captured"

    # ensure history buffer appended copies
    assert metrics.history_buffer and isinstance(metrics.history_buffer[0], dict)


def test_apply_tick_does_not_mutate_input_tick() -> None:
    metrics = Metrics()
    tick = _make_tick()
    original = json.loads(json.dumps(tick))  # deep clone via JSON

    apply_tick_to_metrics(metrics, tick)

    assert tick == original, "apply_tick_to_metrics should not mutate the original tick"


def test_apply_tick_sanitises_alert_flags_to_bool() -> None:
    metrics = Metrics()
    tick = _make_tick()
    tick["alert_flags"] = {
        "load_factor": "true",
        "avg_probe_estimate": 1,
        "tombstone_ratio": None,
        "probing": "FALSE",
    }

    apply_tick_to_metrics(metrics, tick)

    assert metrics.alert_flags == {
        "load_factor": True,
        "avg_probe_estimate": True,
        "tombstone_ratio": False,
        "probing": False,
    }


def test_apply_tick_prunes_invalid_latency_entries() -> None:
    metrics = Metrics()
    metrics.latency_summary_stats = {"overall": {"count": 1, "sum": 2.0}}
    metrics.latency_histograms = {"overall": [(1.0, 1)]}

    tick = _make_tick()
    tick["latency_summary_stats"] = {"overall": {"count": "bad", "sum": "nan"}, "extra": 5}
    tick["latency_histograms"] = {
        "overall": [
            {"le": "nan", "count": 1},
            {"le": 0.5, "count": "bad"},
            {"le": 0.5, "count": 2},
        ],
        "invalid": "value",
    }

    apply_tick_to_metrics(metrics, tick)

    # Only the valid bucket should survive
    assert metrics.latency_histograms == {"overall": [(0.5, 2)]}
    # Summary stats should be cleared because no numeric data provided
    assert metrics.latency_summary_stats == {"overall": {}}


def test_apply_tick_only_appends_dict_events() -> None:
    metrics = Metrics()
    tick = _make_tick()
    tick["events"] = [{"type": "info"}, "bad", None]

    apply_tick_to_metrics(metrics, tick)

    assert list(metrics.events_history) == [{"type": "info"}]


def test_format_bucket_label_handles_infinity() -> None:
    assert format_bucket_label(math.inf) == "+Inf"
    assert format_bucket_label(1.23456789) == "1.234568"


def test_parse_tick_line_filters_invalid_entries(_caplog: pytest.LogCaptureFixture) -> None:
    assert parse_tick_line("not-json") is None
    assert parse_tick_line(json.dumps([])) is None
    assert parse_tick_line(json.dumps({"schema": "unknown"})) is None
    from adhash.metrics.constants import TICK_SCHEMA

    valid = parse_tick_line(json.dumps({"schema": TICK_SCHEMA, "ops": 1}))
    assert valid == {"schema": TICK_SCHEMA, "ops": 1}


def test_stream_metrics_file_handles_missing_path(
    tmp_path: Path, _caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "missing.ndjson"
    calls: list[dict[str, Any]] = []
    stream_metrics_file(missing, follow=False, callback=calls.append, poll_interval=0.01)
    assert not calls


def test_threshold_watchdog_emits_alerts_and_resets(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="hashmap_cli")
    policy = WatchdogPolicy(
        enabled=True, load_factor_warn=0.5, avg_probe_warn=1.0, tombstone_ratio_warn=None
    )
    watchdog = ThresholdWatchdog(policy)

    tick = {
        "backend": "adaptive",
        "load_factor": 0.75,
        "avg_probe_estimate": 2.0,
        "tombstone_ratio": 0.1,
    }
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


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, True),
        (False, False),
        ("True", True),
        (" off ", False),
        ("1", True),
        ("0", False),
        ("ON", True),
        ("OFF", False),
        ("maybe", True),
        (1, True),
        (0, False),
        (None, False),
        ([], False),
        ({}, False),
        (object(), True),
    ],
)
def test_coerce_alert_flag_normalises_inputs(value: Any, expected: bool) -> None:
    assert _coerce_alert_flag(value) is expected
