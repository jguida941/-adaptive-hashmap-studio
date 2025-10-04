from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

import pytest

pytest.importorskip("tomllib")

from adhash.cli.commands import _configure_workload_dna
from adhash.workloads import WorkloadDNAResult, format_workload_dna


class DummyContext:
    def __init__(self, result: WorkloadDNAResult) -> None:
        self._result = result
        self._captured: list[str] = []
        self._captured_payload: list[dict[str, object]] = []

    def analyze_workload(self, csv_path: str, top_keys: int, max_tracked_keys: int) -> WorkloadDNAResult:
        assert Path(csv_path).name == "sample.csv"
        assert top_keys == 10
        assert max_tracked_keys == 200_000
        return self._result

    def emit_success(self, command: str, *, text: str | None = None, data: dict[str, object] | None = None) -> None:
        assert command == "workload-dna"
        if text is not None:
            self._captured.append(text)
        if data is not None:
            self._captured_payload.append(data)

    def json_enabled(self) -> bool:  # pragma: no cover - default path toggled manually
        return False

    @property
    def logger(self):  # pragma: no cover - unused by handler
        raise RuntimeError("logger should not be accessed in this test")


@pytest.fixture
def sample_result() -> WorkloadDNAResult:
    return WorkloadDNAResult(
        schema="workload_dna.v1",
        csv_path="/tmp/sample.csv",
        file_size_bytes=1234,
        total_rows=100,
        op_counts={"put": 40, "get": 50, "del": 10},
        op_mix={"put": 0.4, "get": 0.5, "del": 0.1},
        mutation_fraction=0.5,
        unique_keys_estimated=30,
        key_space_depth=3.33,
        key_length_stats={"count": 100, "mean": 4.0, "min": 3.0, "max": 6.0, "stdev": 0.5},
        value_size_stats={"count": 40, "mean": 5.0, "min": 1.0, "max": 12.0, "stdev": 2.0},
        key_entropy_bits=3.2,
        key_entropy_normalised=0.8,
        hot_keys=({"key": "alpha", "count": 20.0, "share": 0.2},),
        coverage_targets={"p50": 2, "p80": 4, "p95": 6},
        numeric_key_fraction=0.25,
        sequential_numeric_step_fraction=0.1,
        adjacent_duplicate_fraction=0.05,
        hash_collision_hotspots={"0x010": 3},
        bucket_counts=tuple([8, 4, 2, 1] + [0] * ((1 << 12) - 4)),
        bucket_percentiles={"p50": 0.0, "p75": 0.5, "p90": 1.5, "p95": 2.5, "p99": 3.5},
        collision_depth_histogram={0: (1 << 12) - 4, 1: 1, 2: 1, 3: 1, 4: 1},
        non_empty_buckets=4,
        max_bucket_depth=4,
    )


def test_format_workload_dna(sample_result: WorkloadDNAResult) -> None:
    text = format_workload_dna(sample_result)
    assert "Workload DNA" in text
    assert "Hot keys" in text
    assert "Coverage" in text
    assert "0x010" in text


def test_workload_dna_handler_emits_summary(sample_result: WorkloadDNAResult) -> None:
    ctx = DummyContext(sample_result)
    parser = ArgumentParser()
    handler = _configure_workload_dna(parser, ctx)  # type: ignore[arg-type]
    args = parser.parse_args(["--csv", "sample.csv"])

    handler(args)

    assert ctx._captured, "expected summary text to be emitted"
    assert "Workload DNA" in ctx._captured[0]
    assert ctx._captured_payload
    dna_payload = ctx._captured_payload[0]["dna"]  # type: ignore[index]
    assert isinstance(dna_payload, dict)
    assert dna_payload["total_rows"] == 100
    assert "bucket_counts" in dna_payload
    assert len(dna_payload["bucket_counts"]) == 1 << 12
    assert dna_payload["bucket_percentiles"]["p95"] >= 1.0
