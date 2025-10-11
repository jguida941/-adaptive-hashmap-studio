"""FastAPI application for the Adaptive Hash Map control surface."""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Iterable, Iterator
from typing import TYPE_CHECKING, Any, Protocol, cast

from starlette.requests import Request as StarletteRequest

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.responses import Response as FastResponse
    from fastapi.responses import StreamingResponse as FastStreamingResponse

from .jobs import JobManager
from .models import (
    BatchRequest,
    JobCreated,
    JobDetail,
    JobLogEntryModel,
    JobState,
    JobStatusResponse,
    ProfileRequest,
    RunCsvRequest,
)


class JobLogEntryLike(Protocol):
    def to_model(self) -> JobLogEntryModel: ...


class JobRecordLike(Protocol):
    id: str
    status: JobState

    def to_detail(self) -> JobDetail: ...


class JobManagerProtocol(Protocol):
    def list(self) -> Iterable[JobRecordLike]: ...

    def run_csv(self, request: RunCsvRequest) -> JobRecordLike: ...

    def profile(self, request: ProfileRequest) -> JobRecordLike: ...

    def batch(self, request: BatchRequest) -> JobRecordLike: ...

    def get(self, job_id: str) -> JobRecordLike: ...

    def iter_logs(self, job_id: str) -> Iterable[JobLogEntryLike]: ...

    def cancel(self, job_id: str) -> bool: ...


def create_app(manager: JobManagerProtocol | None = None) -> Any:
    """Create a FastAPI application wired to the given job manager."""

    fastapi_mod = importlib.import_module("fastapi")
    responses_mod = importlib.import_module("fastapi.responses")

    fastapi_cls = fastapi_mod.FastAPI
    depends = fastapi_mod.Depends
    http_exception = fastapi_mod.HTTPException
    status = fastapi_mod.status
    response_cls = responses_mod.Response
    streaming_response_cls = responses_mod.StreamingResponse

    job_manager: JobManagerProtocol
    job_manager = JobManager() if manager is None else manager
    app = cast(
        "FastAPI",
        fastapi_cls(title="Adaptive Hash Map Control Surface", version="0.1.0"),
    )
    app.state.job_manager = job_manager

    token_value = os.getenv("ADHASH_TOKEN")

    async def require_token(request: StarletteRequest) -> None:
        if not token_value:
            return
        authorization = request.headers.get("Authorization")
        if authorization == f"Bearer {token_value}":
            return
        if request.query_params.get("token") == token_value:
            return
        raise http_exception(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    def get_manager() -> JobManagerProtocol:
        return cast(JobManagerProtocol, app.state.job_manager)

    manager_dep = depends(get_manager)

    @app.get("/healthz", response_model=dict)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=dict)
    def ready() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/jobs", response_model=JobStatusResponse, dependencies=[depends(require_token)])
    def list_jobs(
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> JobStatusResponse:
        jobs = [record.to_detail() for record in manager.list()]
        return JobStatusResponse(jobs=jobs)

    @app.post(
        "/api/jobs/run-csv",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[depends(require_token)],
    )
    def run_csv_endpoint(
        request: RunCsvRequest,
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> JobCreated:
        try:
            record = manager.run_csv(request)
        except ValueError as exc:
            raise http_exception(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return JobCreated(id=record.id, status=JobState.PENDING)

    @app.post(
        "/api/jobs/profile",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[depends(require_token)],
    )
    def profile_endpoint(
        request: ProfileRequest,
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> JobCreated:
        try:
            record = manager.profile(request)
        except ValueError as exc:
            raise http_exception(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return JobCreated(id=record.id, status=JobState.PENDING)

    @app.post(
        "/api/jobs/batch",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[depends(require_token)],
    )
    def batch_endpoint(
        request: BatchRequest,
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> JobCreated:
        try:
            record = manager.batch(request)
        except ValueError as exc:
            raise http_exception(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return JobCreated(id=record.id, status=JobState.PENDING)

    @app.get(
        "/api/jobs/{job_id}",
        response_model=JobDetail,
        dependencies=[depends(require_token)],
    )
    def job_detail(
        job_id: str,
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> JobDetail:
        try:
            record = manager.get(job_id)
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise http_exception(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            ) from exc
        return record.to_detail()

    @app.get(
        "/api/jobs/{job_id}/logs",
        dependencies=[depends(require_token)],
    )
    def job_logs(
        job_id: str,
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> Any:
        try:
            logs = manager.iter_logs(job_id)
        except KeyError as exc:
            raise http_exception(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            ) from exc

        log_models: list[JobLogEntryModel] = [entry.to_model() for entry in logs]

        def _iter() -> Iterator[str]:
            for entry in log_models:
                yield json.dumps(entry.model_dump(), ensure_ascii=False) + "\n"

        response = streaming_response_cls(_iter(), media_type="application/x-ndjson")
        return cast("FastStreamingResponse", response)

    @app.delete(
        "/api/jobs/{job_id}",
        response_class=response_cls,
        status_code=status.HTTP_204_NO_CONTENT,
        response_model=None,
        dependencies=[depends(require_token)],
    )
    def cancel_job(
        job_id: str,
        manager: JobManagerProtocol = manager_dep,  # noqa: B008 - FastAPI dependency wiring
    ) -> Any:
        try:
            record = manager.get(job_id)
        except KeyError as exc:
            raise http_exception(
                status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
            ) from exc
        cancelled = manager.cancel(job_id)
        if not cancelled and record.status not in {
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            raise http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job is already running and could not be cancelled.",
            )
        response = response_cls(status_code=status.HTTP_204_NO_CONTENT)
        return cast("FastResponse", response)

    return app


__all__ = ["create_app", "JobManagerProtocol"]
