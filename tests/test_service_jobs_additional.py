import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, cast

import pytest

from adhash.batch.runner import JobResult, JobSpec
from adhash.service.jobs import JobManager, _serialize_batch_result
from adhash.service.models import BatchRequest, ProfileRequest, RunCsvRequest


@pytest.fixture
def job_manager(tmp_path: Path):
    manager = JobManager(base_dir=tmp_path / "jobs", max_workers=1)
    try:
        yield manager
    finally:
        manager.shutdown()


def test_prepare_path_handles_relative_and_absolute(tmp_path: Path):
    work = tmp_path / "workspace"
    work.mkdir()
    absolute = tmp_path / "data.csv"
    absolute.write_text("csv", encoding="utf-8")

    resolved_absolute = JobManager._prepare_path(str(absolute), work)
    assert resolved_absolute == str(absolute.resolve())

    relative = JobManager._prepare_path("relative.txt", work)
    assert relative == str((work / "relative.txt").resolve())
    assert JobManager._prepare_optional_path(None, work) is None


def test_append_log_and_capture_output(job_manager: JobManager):
    record = job_manager._create_job("test", {"input": "csv"})
    job_manager._append_log(record.id, "first log", "INFO")
    log_path = job_manager.base_dir / record.id / "logs.ndjson"
    assert log_path.exists()

    with job_manager._capture_output(record.id):
        print("captured stdout")
        logging.getLogger("hashmap_cli").info("info message")

    stored = job_manager.iter_logs(record.id)
    messages = [entry.message for entry in stored]
    assert any("captured stdout" in message for message in messages)
    assert any("info message" in message for message in messages)


def test_execute_run_csv_resolves_artifacts(
    job_manager: JobManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    outputs: Dict[str, Any] = {}

    def fake_run_csv(csv_path: str, mode: str, **kwargs):
        outputs["csv"] = csv_path
        outputs["kwargs"] = kwargs
        return {"status": "ok", "mode": mode}

    monkeypatch.setattr("adhash.service.jobs.run_csv", fake_run_csv)

    request = RunCsvRequest(
        csv="input/workload.csv",
        mode="adaptive",
        snapshot_out="snapshots/out.snapshot",
        json_summary_out="summary.json",
        metrics_out_dir="metrics",
        metrics_host=None,
        metrics_host_env_fallback=False,
        working_dir=str(tmp_path / "work"),
    )

    result, artifacts = job_manager._execute_run_csv("job", request)
    assert result["status"] == "ok"
    assert artifacts["snapshot_out"].endswith("snapshots/out.snapshot")
    assert artifacts["json_summary_out"].endswith("summary.json")
    assert artifacts["metrics_out_dir"].endswith("metrics")
    kwargs = cast(Dict[str, Any], outputs["kwargs"])
    assert kwargs["metrics_host"] == "127.0.0.1"


def test_execute_profile_returns_summary(
    job_manager: JobManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("adhash.service.jobs.profile_csv", lambda path, sample_limit: "fast")

    request = ProfileRequest(csv=str(tmp_path / "input.csv"), sample_limit=50)
    result, artifacts = job_manager._execute_profile("job", request)
    assert result["recommended_mode"] == "fast"
    assert artifacts == {}


def test_execute_batch_serializes_results(
    job_manager: JobManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    spec_obj = SimpleNamespace(
        name="batch",
        command="run",
        csv=tmp_path / "workload.csv",
        mode="adaptive",
        report_path=tmp_path / "report.txt",
        html_report_path=tmp_path / "report.html",
    )

    run_results = [
        JobResult(
            spec=cast(JobSpec, spec_obj),
            exit_code=0,
            duration_seconds=1.5,
            stdout="out",
            stderr="err",
            summary={"ops": 10},
        )
    ]

    class FakeRunner:
        def __init__(self, spec):
            assert spec is spec_obj

        def run(self):
            return run_results

    monkeypatch.setattr("adhash.service.jobs.load_spec", lambda path: spec_obj)
    monkeypatch.setattr("adhash.service.jobs.BatchRunner", FakeRunner)

    request = BatchRequest(spec_path=str(tmp_path / "spec.toml"))
    result, artifacts = job_manager._execute_batch("job", request)
    assert result["status"] == "completed"
    assert artifacts["report"].endswith("report.txt")
    assert artifacts["html_report"].endswith("report.html")
    serialized = _serialize_batch_result(run_results[0])
    assert serialized["summary"] == {"ops": 10}


def test_cancel_returns_false_for_unknown_future(job_manager: JobManager):
    record = job_manager._create_job("test", {"alpha": 1})
    # Cancellation should fail because future not registered yet.
    assert job_manager.cancel(record.id) is False
