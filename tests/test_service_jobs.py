from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic")

from adhash.service.jobs import JobManager
from adhash.service.models import JobState, ProfileRequest, RunCsvRequest


@pytest.fixture(name="tiny_csv")
def tiny_csv_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.csv"
    path.write_text("op,key,value\nput,A,1\nget,A,\n", encoding="utf-8")
    return path


def test_run_csv_job_completes(tmp_path: Path, tiny_csv: Path) -> None:
    jobs_root = tmp_path / "jobs"
    manager = JobManager(base_dir=jobs_root, max_workers=1)
    try:
        request = RunCsvRequest(
            csv=str(tiny_csv),
            mode="adaptive",
            dry_run=True,
            json_summary_out=str(tmp_path / "summary.json"),
        )
        record = manager.run_csv(request)
        finished = manager.wait(record.id, timeout=10.0)
        assert finished.status is JobState.COMPLETED
        assert finished.result is not None
        # Logs should include at least the start and completion messages.
        logs = list(manager.iter_logs(record.id))
        assert len(logs) >= 2
        assert any("Job completed" in entry.message for entry in logs)
        assert any("validation successful" in entry.message.lower() for entry in logs)
        result_path = jobs_root / record.id / "result.json"
        assert result_path.exists()
        content = json.loads(result_path.read_text(encoding="utf-8"))
        assert content["status"] in {"running", "validated", "completed"}
    finally:
        manager.shutdown()


def test_profile_job_returns_recommendation(tmp_path: Path, tiny_csv: Path) -> None:
    manager = JobManager(base_dir=tmp_path / "jobs")
    try:
        request = ProfileRequest(csv=str(tiny_csv), sample_limit=10)
        record = manager.profile(request)
        finished = manager.wait(record.id, timeout=10.0)
        assert finished.status is JobState.COMPLETED
        assert finished.result is not None
        assert "recommended_mode" in finished.result
    finally:
        manager.shutdown()
