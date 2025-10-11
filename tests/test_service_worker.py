from unittest import mock

from adhash.service.worker import JobWorker


def test_job_worker_runs_target_and_updates_manager() -> None:
    manager = mock.Mock()

    def job_fn(*args: object, **kwargs: object) -> tuple[dict[str, object], dict[str, str]]:
        return {"result": args, "kwargs": kwargs}, {"artifact": "path"}

    worker = JobWorker(
        job_id="job-123",
        manager=manager,
        description="demo job",
        target=job_fn,
        args=("alpha",),
        kwargs={"beta": 2},
    )

    result = worker()

    manager._mark_running.assert_called_once_with("job-123")
    manager._append_log.assert_called_once_with("job-123", "Starting demo job", "INFO")
    manager._mark_completed.assert_called_once_with(
        "job-123",
        {"result": ("alpha",), "kwargs": {"beta": 2}},
        {"artifact": "path"},
    )
    manager._mark_failed.assert_not_called()
    assert result == {"result": ("alpha",), "kwargs": {"beta": 2}}
