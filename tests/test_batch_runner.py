from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

from adhash.batch.runner import BatchRunner, BatchSpec, JobResult, JobSpec, load_spec


def _locate_workload(name: str) -> Path:
    """Find a workload CSV even when tests run from a mutated copy of the repo."""
    seen: set[Path] = set()
    for candidate in (Path.cwd(), *Path(__file__).resolve().parents):
        root = candidate.resolve()
        if root in seen:
            continue
        seen.add(root)
        csv_path = (root / "data" / "workloads" / name).resolve()
        if csv_path.exists():
            return csv_path

    raise RuntimeError(f"Unable to locate workload CSV: {name}")


@pytest.fixture()
def spec_file(tmp_path: Path) -> Path:
    csv = _locate_workload("w_uniform.csv")
    spec = tmp_path / "batch.toml"
    spec.write_text(
        """
        [batch]
        hashmap_cli = "-m hashmap_cli"
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
        """.format(
            csv=csv
        )
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


def test_write_report_escapes_html(tmp_path: Path) -> None:
    spec = BatchSpec(
        jobs=[],
        report_path=tmp_path / "report.md",
        working_dir=tmp_path,
        hashmap_cli=["-m", "hashmap_cli"],
        html_report_path=tmp_path / "report.html",
    )
    runner = BatchRunner(spec)

    job_spec = JobSpec(name="job-<script>", command="run-csv", csv=Path("input.csv"))
    result = JobResult(
        spec=job_spec,
        exit_code=0,
        duration_seconds=1.0,
        stdout="<script>alert(1)</script>",
        stderr="",
        summary={
            "ops_per_second": 1234,
            "backend": "adaptive",
            "latency_ms": {"overall": {"p99": 1.23}},
        },
    )

    runner._write_report([result])

    assert spec.report_path.exists()
    assert spec.html_report_path and spec.html_report_path.exists()
    html = spec.html_report_path.read_text()

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "job-&lt;script&gt;" in html


def test_metrics_summary_is_capped(tmp_path: Path) -> None:
    spec = BatchSpec(
        jobs=[],
        report_path=tmp_path / "report.md",
        working_dir=tmp_path,
        hashmap_cli=["-m", "hashmap_cli"],
        html_report_path=tmp_path / "report.html",
    )
    runner = BatchRunner(spec)

    results: List[JobResult] = []
    for idx in range(BatchRunner._MAX_SUMMARY_ROWS + 50):
        job_spec = JobSpec(name=f"job-{idx}", command="run-csv", csv=Path("input.csv"))
        summary = {
            "ops_per_second": 1000 + idx,
            "backend": "adaptive",
            "latency_ms": {"overall": {"p99": 0.5}},
        }
        results.append(
            JobResult(
                spec=job_spec,
                exit_code=0,
                duration_seconds=1.0,
                stdout="",
                stderr="",
                summary=summary,
            )
        )

    runner._write_report(results)

    markdown = spec.report_path.read_text()
    capture = False
    table_lines: List[str] = []
    for line in markdown.splitlines():
        if line.startswith("## Comparative Summary"):
            capture = True
            continue
        if capture:
            if not line or not line.startswith("|"):
                if table_lines:
                    break
                continue
            table_lines.append(line)

    assert len(table_lines) >= 2  # header + divider
    data_rows = table_lines[2:]
    assert len(data_rows) == BatchRunner._MAX_SUMMARY_ROWS


def test_run_job_handles_launch_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    job_spec = JobSpec(name="broken", command="profile", csv=Path("input.csv"))
    spec = BatchSpec(
        jobs=[job_spec],
        report_path=tmp_path / "report.md",
        working_dir=tmp_path,
        hashmap_cli=["-m", "hashmap_cli"],
    )
    runner = BatchRunner(spec)

    def _raise(*_args, **_kwargs):
        raise FileNotFoundError("python not found")

    monkeypatch.setattr(subprocess, "run", _raise)

    caplog.set_level("ERROR")
    result = runner._run_job(job_spec)
    assert result.exit_code == 1
    assert "python not found" in result.stderr
    assert "broken" in caplog.text
