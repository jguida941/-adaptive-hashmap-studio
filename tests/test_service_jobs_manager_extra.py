from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Any, cast

import pytest

from adhash.service.jobs import JobLogEntry, JobManager, JobRecord, JobState
from adhash.service.models import BatchRequest
from adhash.service.worker import JobWorker


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_job_manager_warns_on_invalid_max_jobs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("ADHASH_MAX_JOBS", "not-a-number")
    base_dir = tmp_path / "jobs"
    with caplog.at_level(logging.WARNING):
        manager = JobManager(base_dir=base_dir)
    try:
        assert any("Invalid ADHASH_MAX_JOBS" in record.message for record in caplog.records)
        assert manager._executor._max_workers == 4  # falls back to default
    finally:
        manager.shutdown()
        monkeypatch.delenv("ADHASH_MAX_JOBS", raising=False)


def test_job_manager_log_and_detail_roundtrip(tmp_path: Path) -> None:
    manager = JobManager(base_dir=tmp_path / "jobs")
    try:
        record = manager._create_job("run-csv", {"csv": "data.csv"})
        manager._append_log(record.id, "hello world", "INFO")
        logs = list(manager.iter_logs(record.id))
        assert logs
        model = logs[0].to_model()
        assert model.message == "hello world"

        detail = record.to_detail()
        assert detail.id == record.id
        assert detail.kind == "run-csv"

        log_path = manager.base_dir / record.id / "logs.ndjson"
        log_entries = [
            json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
        ]
        assert log_entries[0]["message"] == "hello world"
    finally:
        manager.shutdown()


def test_job_manager_mark_completed_and_failed(tmp_path: Path) -> None:
    manager = JobManager(base_dir=tmp_path / "jobs")
    try:
        record = manager._create_job("run-csv", {"csv": "ops.csv"})
        manager._mark_running(record.id)
        manager._mark_completed(record.id, {"status": "ok"}, {"artifact": "path/out.txt"})

        completed = manager.get(record.id)
        assert completed.status == JobState.COMPLETED
        result_payload = _read_json(manager.base_dir / record.id / "result.json")
        assert result_payload["status"] == "ok"
        artifacts_payload = _read_json(manager.base_dir / record.id / "artifacts.json")
        assert artifacts_payload["artifact"] == "path/out.txt"

        failed_record = manager._create_job("profile", {"csv": "ops.csv"})
        manager._mark_failed(failed_record.id, RuntimeError("boom"))
        failed = manager.get(failed_record.id)
        assert failed.status == JobState.FAILED
        error_text = (manager.base_dir / failed_record.id / "error.txt").read_text(encoding="utf-8")
        assert "boom" in error_text
    finally:
        manager.shutdown()


def test_job_manager_batch_schedules_job(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = JobManager(base_dir=tmp_path / "jobs")

    class FakeWorker:
        def __init__(
            self,
            *,
            job_id: str,
            manager: JobManager,
            description: str,
            target: Callable[..., Any],
            args: tuple[Any, ...],
        ) -> None:
            self.job_id = job_id
            self.manager = manager
            self.description = description
            self.target = target
            self.args = args

        def __call__(self) -> Any:
            return self.target(*self.args)

    captured: dict[str, Any] = {}

    def fake_submit(record: Any, worker: Any) -> None:
        captured["record"] = record
        captured["worker"] = worker

    monkeypatch.setattr("adhash.service.jobs.JobWorker", lambda **kwargs: FakeWorker(**kwargs))
    monkeypatch.setattr(manager, "_submit", fake_submit)

    try:
        job_record = manager.batch(BatchRequest(spec_path="spec.toml"))
        worker = captured["worker"]
        assert captured["record"].id == job_record.id
        assert worker.job_id == job_record.id
        assert "batch spec.toml" in worker.description
        assert worker.args[0] == job_record.id
    finally:
        manager.shutdown()


def test_submit_cleanup_and_cancel(_monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manager = JobManager(base_dir=tmp_path / "jobs")

    class FakeFuture:
        def __init__(self) -> None:
            self._callbacks: list[Callable[[FakeFuture], None]] = []
            self._cancelled = False

        def add_done_callback(self, cb: Callable[[FakeFuture], None]) -> None:
            self._callbacks.append(cb)

        def cancel(self) -> bool:
            self._cancelled = True
            return True

        def exception(self) -> Any:
            if self._cancelled:
                raise CancelledError()
            return None

        def result(self, _timeout: object | None = None) -> Any:
            if self._cancelled:
                raise CancelledError()
            return None

        def run_callbacks(self) -> None:
            for cb in list(self._callbacks):
                cb(self)

    class FakeExecutor:
        def __init__(self) -> None:
            self.submitted: list[Any] = []

        def submit(self, worker: Any) -> FakeFuture:
            self.submitted.append(worker)
            return FakeFuture()

        def shutdown(self, _wait: bool = True, _cancel_futures: bool = False) -> None:
            return None

    fake_executor = FakeExecutor()
    manager._executor = cast(Any, fake_executor)

    try:
        record = manager._create_job("test", {"value": 1})

        worker = JobWorker(
            job_id=record.id,
            manager=manager,
            description="noop",
            target=lambda: ({"status": "ok"}, {}),
        )
        manager._submit(record, worker)
        future = manager._futures[record.id]
        assert fake_executor.submitted
        cast(FakeFuture, future).run_callbacks()
        assert record.id not in manager._futures

        worker2 = JobWorker(
            job_id=record.id,
            manager=manager,
            description="noop",
            target=lambda: ({"status": "done"}, {}),
        )
        manager._submit(record, worker2)
        future2 = manager._futures[record.id]
        assert manager.cancel(record.id) is True
        cancelled_record = manager.get(record.id)
        assert cancelled_record.status == JobState.CANCELLED
        cast(FakeFuture, future2).run_callbacks()
        assert record.id not in manager._futures
    finally:
        manager.shutdown()


def test_job_log_entry_and_record_models(tmp_path: Path) -> None:
    entry = JobLogEntry(timestamp=123.0, level="INFO", message="hello")
    model = entry.to_model()
    assert model.level == "INFO"
    assert model.message == "hello"

    record = JobRecord(
        id="job-1",
        kind="run-csv",
        status=JobState.PENDING,
        request={"csv": "data.csv"},
        created_at=1.0,
        updated_at=2.0,
        path=tmp_path,
        result={"status": "ok"},
        error=None,
        artifacts={"report": "report.txt"},
    )
    detail = record.to_detail()
    assert detail.id == "job-1"
    assert detail.artifacts["report"] == "report.txt"


def test_job_manager_wait_handles_future(tmp_path: Path) -> None:
    manager = JobManager(base_dir=tmp_path / "jobs", max_workers=1)
    try:
        record = manager._create_job("test", {"value": 1})

        class FutureStub:
            def __init__(self) -> None:
                self.waited = False

            def result(self, timeout: float | None = None) -> None:  # noqa: ARG002
                self.waited = True

        stub = FutureStub()
        manager._futures[record.id] = stub  # type: ignore[assignment]
        waited = manager.wait(record.id)
        assert waited.id == record.id
        assert stub.waited is True

        manager._futures.pop(record.id, None)
        waited_again = manager.wait(record.id)
        assert waited_again.id == record.id
    finally:
        manager.shutdown()
