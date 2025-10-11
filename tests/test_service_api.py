from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pydantic")

from fastapi.testclient import TestClient

from adhash.service import JobManager, JobState, RunCsvRequest, create_app


def _write_csv(path: Path) -> None:
    path.write_text("op,key,value\nput,A,1\nget,A,\n", encoding="utf-8")


def _iter_log_lines(payload: str) -> Iterable[dict[str, Any]]:
    for line in payload.splitlines():
        if line.strip():
            yield json.loads(line)


def test_run_csv_endpoint(tmp_path: Path) -> None:
    csv_path = tmp_path / "tiny.csv"
    _write_csv(csv_path)
    jobs_root = tmp_path / "jobs"
    manager = JobManager(base_dir=jobs_root, max_workers=1)
    app = create_app(manager)
    client = TestClient(app)
    try:
        response = client.post(
            "/api/jobs/run-csv",
            json=RunCsvRequest(csv=str(csv_path), mode="adaptive", dry_run=True).model_dump(),
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        manager.wait(job_id, timeout=10.0)

        detail = client.get(f"/api/jobs/{job_id}")
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["status"] == JobState.COMPLETED.value

        logs_response = client.get(f"/api/jobs/{job_id}/logs")
        assert logs_response.status_code == 200
        logs = list(_iter_log_lines(logs_response.text))
        assert logs
        assert any("completed" in entry["message"] for entry in logs)

        listing = client.get("/api/jobs")
        assert listing.status_code == 200
        jobs = listing.json()["jobs"]
        assert any(item["id"] == job_id for item in jobs)
    finally:
        manager.shutdown()
        client.close()


def test_service_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")
    jobs_root = tmp_path / "jobs"
    manager = JobManager(base_dir=jobs_root, max_workers=1)
    app = create_app(manager)
    client = TestClient(app)
    try:
        response = client.get("/api/jobs")
        assert response.status_code == 401

        authed = client.get("/api/jobs", headers={"Authorization": "Bearer secret"})
        assert authed.status_code == 200
        assert "jobs" in authed.json()
    finally:
        manager.shutdown()
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)


def test_cancel_job_idempotent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ADHASH_TOKEN", "secret")
    jobs_root = tmp_path / "jobs"
    manager = JobManager(base_dir=jobs_root, max_workers=1)
    record = manager._create_job("dummy", {"payload": "test"})
    record.status = JobState.CANCELLED
    record.updated_at = record.created_at
    manager._write_status(record)

    app = create_app(manager)
    client = TestClient(app)
    try:
        response = client.delete(
            f"/api/jobs/{record.id}", headers={"Authorization": "Bearer secret"}
        )
        assert response.status_code == 204

        response2 = client.delete(
            f"/api/jobs/{record.id}", headers={"Authorization": "Bearer secret"}
        )
        assert response2.status_code == 204
    finally:
        manager.shutdown()
        client.close()
        monkeypatch.delenv("ADHASH_TOKEN", raising=False)
