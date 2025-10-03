from __future__ import annotations

from collections import deque
from importlib import util
from typing import Deque, Dict
import sys

from pathlib import Path

CLI_PATH = Path(__file__).resolve().parents[1] / "hashmap_cli.py"
spec = util.spec_from_file_location("hashmap_cli", CLI_PATH)
assert spec and spec.loader
cli = util.module_from_spec(spec)
sys.modules["hashmap_cli"] = cli
spec.loader.exec_module(cli)  # type: ignore[call-arg]


def test_apply_tick_to_metrics_updates_counters() -> None:
    metrics = cli.Metrics()
    history: Deque[Dict[str, object]] = deque(maxlen=3)
    metrics.history_buffer = history

    tick = {
        "schema": "metrics.v1",
        "backend": "adaptive",
        "ops": 256,
        "ops_by_type": {"put": 64, "get": 160, "del": 32},
        "migrations": 1,
        "compactions": 0,
        "load_factor": 0.42,
        "max_group_len": 3,
        "avg_probe_estimate": 1.2,
        "tombstone_ratio": 0.01,
        "latency_ms": {"overall": {"p50": 0.5, "sum": 10.0, "count": 20}},
        "latency_hist_ms": {
            "overall": [
                {"le": 0.5, "count": 10},
                {"le": 1.0, "count": 20},
            ]
        },
        "alerts": [{"metric": "load_factor", "severity": "warning"}],
        "events": [{"type": "migration", "backend": "robinhood", "t": 12.0}]
    }

    cli.apply_tick_to_metrics(metrics, tick)

    assert metrics.ops_total == 256
    assert metrics.puts_total == 64
    assert metrics.backend_name == "adaptive"
    assert metrics.load_factor == 0.42
    assert metrics.active_alerts
    assert metrics.history_buffer is history
    assert history and history[-1]["ops"] == 256
    assert metrics.events_history
