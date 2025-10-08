from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional

import pytest
from fastapi.testclient import TestClient
from typing import cast

from adhash.service.jobs import JobManager

from adhash.service.api import create_app
from adhash.service.models import (
    BatchRequest,
    JobDetail,
    JobLogEntryModel,
    JobState,
    JobStatusResponse,
    ProfileRequest,
    RunCsvRequest,
)


@dataclass
class _StubLog:
    timestamp: float
    level: str
    message: str

    def to_model(self) -> JobLogEntryModel:
        return JobLogEntryModel(timestamp=self.timestamp, level=self.level, message=self.message)


@dataclass
class _StubRecord:
    id: str
    kind: str = "run-csv"
    status: JobState = JobState.PENDING
    request: Dict[str, str] = field(default_factory=dict)
    result: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)

    def to_detail(self) -> JobDetail:
        return JobDetail(
            id=self.id,
            kind=self.kind,
            status=self.status,
            created_at=1.0,
            updated_at=2.0,
            request=self.request,
            result=self.result,
            error=self.error,
            artifacts=self.artifacts,
        )


class _StubManager:
    def __init__(self) -> None:
        self.records: Dict[str, _StubRecord] = {
            "job1": _StubRecord("job1", status=JobState.PENDING, request={"kind": "run"}),
            "done": _StubRecord("done", status=JobState.COMPLETED),
        }
        self.logs: Dict[str, List[_StubLog]] = {"job1": [_StubLog(1.0, "INFO", "hello world")]}
        self.cancelled: List[str] = []

    # API used by routes
    def list(self) -> List[_StubRecord]:
        return list(self.records.values())

    def run_csv(self, request: RunCsvRequest) -> _StubRecord:
        if request.csv == "bad":
            raise ValueError("bad request")
        record = _StubRecord("job-run", request=request.model_dump())
        self.records[record.id] = record
        return record

    def profile(self, request: ProfileRequest) -> _StubRecord:
        if request.csv == "bad":
            raise ValueError("bad request")
        record = _StubRecord("job-profile", request=request.model_dump())
        self.records[record.id] = record
        return record

    def batch(self, request: BatchRequest) -> _StubRecord:
        if request.spec_path == "bad":
            raise ValueError("bad request")
        record = _StubRecord("job-batch", request=request.model_dump())
        self.records[record.id] = record
        return record

    def get(self, job_id: str) -> _StubRecord:
        if job_id not in self.records:
            raise KeyError(job_id)
        return self.records[job_id]

    def iter_logs(self, job_id: str) -> Iterable[_StubLog]:
        return self.logs[job_id]

    def cancel(self, job_id: str) -> bool:
        if job_id == "job1":
            return False
        self.cancelled.append(job_id)
        record = self.records[job_id]
        record.status = JobState.CANCELLED
        return True


@pytest.fixture
def auth_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    manager = cast(JobManager, _StubManager())
    monkeypatch.setenv("ADHASH_TOKEN", "secret")
    app = create_app(manager)
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def _auth_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer secret"}


def test_health_and_readiness_endpoints(auth_client: TestClient) -> None:
    assert auth_client.get("/healthz").json() == {"status": "ok"}
    assert auth_client.get("/readyz").json() == {"status": "ok"}


def test_list_jobs_requires_token(auth_client: TestClient) -> None:
    response = auth_client.get("/api/jobs")
    assert response.status_code == 401
    response = auth_client.get("/api/jobs", headers=_auth_headers())
    payload = JobStatusResponse.model_validate_json(response.text)
    assert payload.jobs


def test_run_csv_endpoint_handles_success_and_errors(auth_client: TestClient) -> None:
    body = {"csv": "sample.csv", "mode": "adaptive"}
    response = auth_client.post("/api/jobs/run-csv", json=body, headers=_auth_headers())
    assert response.status_code == 202
    assert response.json()["status"] == JobState.PENDING

    response = auth_client.post(
        "/api/jobs/run-csv", json={"csv": "bad", "mode": "adaptive"}, headers=_auth_headers()
    )
    assert response.status_code == 400


def test_profile_and_batch_endpoints(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/jobs/profile", json={"csv": "workload.csv"}, headers=_auth_headers()
    )
    assert response.status_code == 202

    bad = auth_client.post("/api/jobs/profile", json={"csv": "bad"}, headers=_auth_headers())
    assert bad.status_code == 400

    response = auth_client.post(
        "/api/jobs/batch", json={"spec_path": "suite.toml"}, headers=_auth_headers()
    )
    assert response.status_code == 202

    bad = auth_client.post("/api/jobs/batch", json={"spec_path": "bad"}, headers=_auth_headers())
    assert bad.status_code == 400


def test_job_detail_and_logs(auth_client: TestClient) -> None:
    detail = auth_client.get("/api/jobs/job1", headers=_auth_headers())
    assert detail.status_code == 200
    assert detail.json()["id"] == "job1"

    logs_response = auth_client.get("/api/jobs/job1/logs", headers=_auth_headers())
    lines = [json.loads(line) for line in logs_response.text.splitlines()]
    assert lines and lines[0]["message"] == "hello world"


def test_cancel_job_handles_conflicts(auth_client: TestClient) -> None:
    conflict = auth_client.delete("/api/jobs/job1", headers=_auth_headers())
    assert conflict.status_code == 409

    done = auth_client.delete("/api/jobs/done", headers=_auth_headers())
    assert done.status_code == 204

    response = auth_client.delete("/api/jobs/job1?token=secret")
    assert response.status_code == 409
