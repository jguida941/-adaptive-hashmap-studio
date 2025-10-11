"""Worker utilities for executing control-surface jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .jobs import JobManager

# Each job target returns (result_payload, artifact_mapping)
JobCallable = Callable[..., tuple[dict[str, Any], dict[str, str]]]


class JobWorker:
    """Callable wrapper that executes a job target under the manager's supervision."""

    def __init__(
        self,
        *,
        job_id: str,
        manager: JobManager,
        description: str,
        target: JobCallable,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        self._job_id = job_id
        self._manager = manager
        self._description = description
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def __call__(self) -> dict[str, Any]:
        return self.run()

    def run(self) -> dict[str, Any]:
        self._manager._mark_running(self._job_id)
        self._manager._append_log(self._job_id, f"Starting {self._description}", "INFO")
        try:
            result, artifacts = self._target(*self._args, **self._kwargs)
        except BaseException as exc:  # pragma: no cover - propagated after bookkeeping
            self._manager._mark_failed(self._job_id, exc)
            raise
        else:
            self._manager._mark_completed(self._job_id, result, artifacts)
            return result


__all__ = ["JobWorker", "JobCallable"]
