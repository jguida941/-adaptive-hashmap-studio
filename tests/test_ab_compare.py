from __future__ import annotations

from pathlib import Path

import json

from adhash.config_toolkit import clone_config
from adhash.hashmap_cli import APP_CONFIG, run_ab_compare


def test_ab_compare_generates_artifacts(tmp_path: Path) -> None:
    csv_path = tmp_path / "workload.csv"
    csv_path.write_text("op,key,value\nput,k1,v1\nget,k1,\n", encoding="utf-8")

    before_cfg = clone_config(APP_CONFIG)

    artifacts_dir = tmp_path / "artifacts"
    json_path = tmp_path / "compare.json"
    markdown_path = tmp_path / "compare.md"

    result = run_ab_compare(
        str(csv_path),
        baseline_label="baseline",
        candidate_label="candidate",
        baseline_mode="adaptive",
        candidate_mode="fast-lookup",
        metrics_dir=str(artifacts_dir),
        json_out=str(json_path),
        markdown_out=str(markdown_path),
        latency_sample_k=8,
        latency_sample_every=1,
        metrics_max_ticks=64,
    )

    assert result["schema"] == "adhash.compare.v1"
    assert result["baseline"]["label"] == "baseline"
    assert result["candidate"]["label"] == "candidate"
    assert "ops_per_second" in result["diff"]
    assert result["timeline"]

    assert json_path.exists()
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["schema"] == "adhash.compare.v1"

    assert markdown_path.exists()
    assert "A/B Comparison" in markdown_path.read_text(encoding="utf-8")

    assert APP_CONFIG == before_cfg

    # metrics artifacts should exist when a directory was provided
    assert any(artifacts_dir.rglob("*.json"))
