from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from adhash.batch.runner import BatchRunner, load_spec


@pytest.fixture()
def spec_file(tmp_path: Path) -> Path:
    repo_root = Path.cwd()
    csv = repo_root / "data/workloads/w_uniform.csv"
    spec = tmp_path / "batch.toml"
    spec.write_text(
        """
        [batch]
        hashmap_cli = "{hashmap_cli}"
        report = "report.md"
        html_report = "report.html"

        [[batch.jobs]]
        name = "profile-uniform"
        command = "profile"
        csv = "{csv}"

        [[batch.jobs]]
        name = "run-uniform"
        command = "run-csv"
        csv = "{csv}"
        json_summary = "uniform.json"
        latency_sample_k = 128
        latency_sample_every = 16
        """.format(hashmap_cli=repo_root / "hashmap_cli.py", csv=csv)
    )
    return spec


def test_batch_runner_executes_jobs(spec_file: Path, tmp_path: Path) -> None:
    spec = load_spec(spec_file)
    runner = BatchRunner(spec, python_executable=sys.executable)
    results = runner.run()

    assert len(results) == 2
    report = spec.report_path
    assert report.exists()
    if spec.html_report_path:
        assert spec.html_report_path.exists()

    run_result = next(r for r in results if r.spec.command == "run-csv")
    assert run_result.exit_code == 0
    assert run_result.summary is not None
    assert "ops_per_second" in run_result.summary

    md = report.read_text()
    assert "run-uniform" in md
    assert "profile-uniform" in md

    json_summary_path = run_result.spec.json_summary
    assert json_summary_path and json_summary_path.exists()
    summary_data = json.loads(json_summary_path.read_text())
    assert summary_data.get("total_ops") == 100000
