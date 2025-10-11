from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adhash.cli import app


def test_run_ab_compare_generates_markdown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    csv_path = tmp_path / "work.csv"
    csv_path.write_text("op,key,value\nput,K1,1\nget,K1,\n", encoding="utf-8")

    baseline_summary = {
        "ops_per_second": 100.0,
        "elapsed_seconds": 1.5,
        "migrations_triggered": 1,
        "compactions_triggered": 0,
        "latency_ms": {"overall": {"p50": 1.0, "p90": 2.0, "p99": 3.0}},
    }
    candidate_summary = {
        "ops_per_second": 110.0,
        "elapsed_seconds": 1.2,
        "migrations_triggered": 0,
        "compactions_triggered": 1,
        "latency_ms": {"overall": {"p50": 0.9, "p90": 1.8, "p99": 2.5}},
    }

    histories = [
        [
            {
                "t": 0.1,
                "ops_per_second_ema": 90.0,
                "ops_per_second_instant": 95.0,
                "load_factor": 0.5,
                "avg_probe_estimate": 2.0,
            }
        ],
        [
            {
                "t": 0.1,
                "ops_per_second_ema": 100.0,
                "ops_per_second_instant": 105.0,
                "load_factor": 0.45,
                "avg_probe_estimate": 1.8,
            }
        ],
    ]

    payloads = [
        {
            "summary": baseline_summary,
            "events": [{"type": "start"}],
            "metrics_file": "baseline.ndjson",
            "history": histories[0],
        },
        {
            "summary": candidate_summary,
            "events": [{"type": "start"}],
            "metrics_file": "candidate.ndjson",
            "history": histories[1],
        },
    ]

    def fake_run_csv(_csv: str, _mode: str, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["capture_history"] is True
        assert kwargs["latency_sample_every"] == 128
        result = payloads.pop(0)
        return dict(result)

    monkeypatch.setitem(app.__dict__, "run_csv", fake_run_csv)

    artifact_dir = tmp_path / "artifacts"
    json_out = tmp_path / "compare.json"
    markdown_out = tmp_path / "compare.md"

    comparison = app.run_ab_compare(
        str(csv_path),
        baseline_label="base",
        candidate_label="cand",
        metrics_dir=str(artifact_dir),
        json_out=str(json_out),
        markdown_out=str(markdown_out),
    )

    assert comparison["schema"] == "adhash.compare.v1"
    assert comparison["baseline"]["label"] == "base"
    assert comparison["candidate"]["label"] == "cand"
    assert comparison["diff"]["ops_per_second"]["delta"] == pytest.approx(10.0)
    assert json_out.exists() and markdown_out.exists()
    assert "artifact_dir" in comparison["metadata"]


def test_delta_packet_and_timeline_helpers() -> None:
    base_summary = {"latency_ms": {"put": {"p50": 1.0}}}
    cand_summary = {"latency_ms": {"put": {"p50": 2.0}}}
    deltas = app._latency_deltas(base_summary, cand_summary)
    entry = deltas["put"]["p50"]
    assert entry["baseline"] == 1.0 and entry["candidate"] == 2.0

    timeline = app._build_timeline(
        [{"t": 0.0, "ops_per_second_ema": 1.0, "load_factor": 0.5, "avg_probe_estimate": 1.0}],
        [{"t": 0.0, "ops_per_second_instant": 2.0, "load_factor": 0.4, "avg_probe_estimate": 0.5}],
    )
    assert timeline[0]["ops"]["delta"] == pytest.approx(1.0)


def test_generate_csv_creates_rows(tmp_path: Path) -> None:
    outfile = tmp_path / "generated.csv"
    app.generate_csv(
        str(outfile),
        ops=5,
        read_ratio=0.4,
        key_skew=1.1,
        key_space=10,
        seed=123,
        del_ratio_within_writes=0.2,
        adversarial_ratio=0.3,
        adversarial_lowbits=2,
    )
    lines = outfile.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6  # header + 5 ops
