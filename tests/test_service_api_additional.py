from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

from fastapi.testclient import TestClient

from adhash.service.api import create_app
from adhash.service.models import JobDetail, JobLogEntryModel, JobState


@dataclass
class FakeRecord:
    id: str
    kind: str
    status: JobState
    created_at: float = 0.0
    updated_at: float = 0.0
    request: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] | None = None
    error: str | None = None
    artifacts: Dict[str, str] = field(default_factory=dict)

    def to_detail(self) -> JobDetail:
        return JobDetail(
            id=self.id,
            kind=self.kind,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            request=self.request,
            result=self.result,
            error=self.error,
            artifacts=self.artifacts,
        )


class FakeLogEntry:
    def __init__(self, message: str, *, level: str = "INFO", timestamp: float = 1.0) -> None:
        self._model = JobLogEntryModel(timestamp=timestamp, level=level, message=message)

    def to_model(self) -> JobLogEntryModel:
        return self._model


class StubManager:
    def __init__(self) -> None:
        self.record = FakeRecord(id="job-1", kind="run-csv", status=JobState.PENDING)
        self.log_entries: List[FakeLogEntry] = [FakeLogEntry("job completed")]  # default log stream
        self.cancel_result = True

    # Interface expected by the API
    def list(self) -> List[FakeRecord]:
        return [self.record]

    def run_csv(self, request: Any) -> FakeRecord:
        return self.record

    def profile(self, request: Any) -> FakeRecord:
        return self.record

    def batch(self, request: Any) -> FakeRecord:
        return self.record

    def get(self, job_id: str) -> FakeRecord:
        if job_id != self.record.id:
            raise KeyError(job_id)
        return self.record

    def iter_logs(self, job_id: str) -> List[FakeLogEntry]:
        self.get(job_id)
        return self.log_entries

    def cancel(self, job_id: str) -> bool:
        self.get(job_id)
        return self.cancel_result


def _make_client(manager: StubManager) -> TestClient:
    app = create_app(manager)
    client = TestClient(app)
    return client


def test_list_jobs_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADHASH_TOKEN", raising=False)
    manager = StubManager()
    client = _make_client(manager)
    try:
        response = client.get("/api/jobs")
        assert response.status_code == 200
        payload = response.json()
        assert payload["jobs"][0]["id"] == manager.record.id
    finally:
        client.close()


def test_list_jobs_accepts_query_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")
    manager = StubManager()
    client = _make_client(manager)
    try:
        response = client.get("/api/jobs", params={"token": "secret"})
        assert response.status_code == 200
        assert response.json()["jobs"][0]["id"] == manager.record.id
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_run_csv_endpoint_returns_bad_request_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")

    class RunCsvErrorManager(StubManager):
        def run_csv(self, request: Any) -> FakeRecord:  # type: ignore[override]
            raise ValueError("invalid csv")

    manager = RunCsvErrorManager()
    client = _make_client(manager)
    try:
        response = client.post(
            "/api/jobs/run-csv",
            params={"token": "secret"},
            json={"csv": "bad.csv", "mode": "adaptive"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "invalid csv"
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_profile_endpoint_returns_bad_request_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")

    class ProfileErrorManager(StubManager):
        def profile(self, request: Any) -> FakeRecord:  # type: ignore[override]
            raise ValueError("profile failed")

    manager = ProfileErrorManager()
    client = _make_client(manager)
    try:
        response = client.post(
            "/api/jobs/profile",
            params={"token": "secret"},
            json={"csv": "test.csv", "sample_limit": 10},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "profile failed"
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_batch_endpoint_returns_bad_request_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")

    class BatchErrorManager(StubManager):
        def batch(self, request: Any) -> FakeRecord:  # type: ignore[override]
            raise ValueError("invalid batch spec")

    manager = BatchErrorManager()
    client = _make_client(manager)
    try:
        response = client.post(
            "/api/jobs/batch",
            params={"token": "secret"},
            json={"spec_path": "suite.toml"},
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "invalid batch spec"
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_job_logs_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")
    manager = StubManager()
    manager.log_entries = [FakeLogEntry("hello world", timestamp=2.0)]
    client = _make_client(manager)
    try:
        response = client.get(f"/api/jobs/{manager.record.id}/logs", params={"token": "secret"})
        assert response.status_code == 200
        lines = [line for line in response.text.splitlines() if line]
        assert len(lines) == 1
        assert "hello world" in lines[0]
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_job_logs_unknown_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")

    class MissingLogsManager(StubManager):
        def iter_logs(self, job_id: str) -> List[FakeLogEntry]:  # type: ignore[override]
            raise KeyError(job_id)

    manager = MissingLogsManager()
    client = _make_client(manager)
    try:
        response = client.get(f"/api/jobs/{manager.record.id}/logs", params={"token": "secret"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Job not found"
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_cancel_job_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")

    class ConflictManager(StubManager):
        def __init__(self) -> None:
            super().__init__()
            self.record.status = JobState.RUNNING
            self.cancel_result = False

    manager = ConflictManager()
    client = _make_client(manager)
    try:
        response = client.delete(f"/api/jobs/{manager.record.id}", params={"token": "secret"})
        assert response.status_code == 409
        assert response.json()["detail"] == "Job is already running and could not be cancelled."
    finally:
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)
