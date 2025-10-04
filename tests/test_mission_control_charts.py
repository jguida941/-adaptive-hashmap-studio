from __future__ import annotations

import math

from adhash.mission_control.widgets import extract_latency_histogram, extract_probe_histogram


def test_extract_latency_histogram_decumulates_counts() -> None:
    payload = {
        "operations": {
            "overall": [
                {"le": "0.001", "count": 3},
                {"le": "0.002", "count": 7},
                {"le": "+Inf", "count": 7},
            ],
            "put": [{"le": "0.001", "count": 1}],
        }
    }

    buckets = list(extract_latency_histogram(payload))

    assert buckets[0] == (0.001, 3)
    assert buckets[1] == (0.002, 4)
    assert buckets[-1] == (math.inf, 0)


def test_extract_latency_histogram_missing_series() -> None:
    assert list(extract_latency_histogram({})) == []


def test_extract_probe_histogram_accepts_lists_and_dicts() -> None:
    payload = {
        "buckets": [
            {"distance": 0, "count": 10},
            (1, 5),
            {"distance": "2", "count": "3"},
            ["bad"],
        ]
    }

    result = list(extract_probe_histogram(payload))

    assert result == [(0, 10), (1, 5), (2, 3)]


def test_extract_probe_histogram_invalid_payload() -> None:
    assert list(extract_probe_histogram({})) == []
