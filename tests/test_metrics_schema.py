import json
from pathlib import Path

from jsonschema import Draft202012Validator

from adhash.metrics import TICK_SCHEMA

SCHEMA = json.loads(Path("src/adhash/contracts/metrics_schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)


def test_metrics_v1_minimal_tick_validates() -> None:
    tick = {
        "schema": TICK_SCHEMA,
        "t": 1.234,
        "backend": "adaptive",
        "ops": 10,
        "load_factor": 0.5,
        "tombstone_ratio": 0.0,
        "latency_ms": {
            "overall": {"p50": 0.1, "p90": 0.2, "p99": 0.3},
            "put": {"p50": 0.1, "p90": 0.2, "p99": 0.3},
        },
        "latency_hist_ms": {
            "overall": [
                {"le": 0.25, "count": 10},
                {"le": 0.5, "count": 20},
                {"le": "+Inf", "count": 25},
            ]
        },
        "ops_by_type": {"put": 3, "get": 7},
    }
    VALIDATOR.validate(tick)


def test_metrics_v1_missing_percentile_rejected() -> None:
    tick = {
        "schema": TICK_SCHEMA,
        "t": 0.0,
        "backend": "adaptive",
        "ops": 0,
        "load_factor": 0.0,
        "latency_ms": {"overall": {"p50": 0, "p90": 0}},
    }
    errors = list(VALIDATOR.iter_errors(tick))
    assert errors and any("p99" in err.message for err in errors)


def test_metrics_v1_alerts_allowed() -> None:
    tick = {
        "schema": TICK_SCHEMA,
        "t": 2.5,
        "backend": "adaptive",
        "ops": 128,
        "load_factor": 0.95,
        "latency_ms": {
            "overall": {"p50": 0.2, "p90": 0.5, "p99": 0.9},
        },
        "alerts": [
            {
                "metric": "load_factor",
                "value": 0.95,
                "threshold": 0.9,
                "severity": "warning",
                "backend": "chaining",
                "message": "Load factor guardrail exceeded: 0.950 ≥ 0.900",
            }
        ],
    }
    VALIDATOR.validate(tick)
