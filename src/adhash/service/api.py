"""FastAPI application for the Adaptive Hash Map control surface."""

from __future__ import annotations

import importlib
import json
import os
from typing import Any, Iterator, List, Optional

from starlette.requests import Request as StarletteRequest

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


def create_app(manager: Optional[JobManager] = None) -> Any:
    """Create a FastAPI application wired to the given job manager."""

    fastapi_mod = importlib.import_module("fastapi")
    responses_mod = importlib.import_module("fastapi.responses")

    FastAPI = fastapi_mod.FastAPI
    Depends = fastapi_mod.Depends
    HTTPException = fastapi_mod.HTTPException
    status = fastapi_mod.status
    Response = responses_mod.Response
    StreamingResponse = responses_mod.StreamingResponse

    job_manager = manager or JobManager()
    app = FastAPI(title="Adaptive Hash Map Control Surface", version="0.1.0")
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    def get_manager() -> JobManager:
        return app.state.job_manager  # type: ignore[return-value]

    @app.get("/healthz", response_model=dict)
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", response_model=dict)
    def ready() -> dict:
        return {"status": "ok"}

    @app.get("/api/jobs", response_model=JobStatusResponse, dependencies=[Depends(require_token)])
    def list_jobs(manager: JobManager = Depends(get_manager)) -> JobStatusResponse:
        jobs = [record.to_detail() for record in manager.list()]
        return JobStatusResponse(jobs=jobs)

    @app.post(
        "/api/jobs/run-csv",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
    )
    def run_csv_endpoint(request: RunCsvRequest, manager: JobManager = Depends(get_manager)) -> JobCreated:
        try:
            record = manager.run_csv(request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return JobCreated(id=record.id, status=JobState.PENDING)

    @app.post(
        "/api/jobs/profile",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
    )
    def profile_endpoint(request: ProfileRequest, manager: JobManager = Depends(get_manager)) -> JobCreated:
        try:
            record = manager.profile(request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return JobCreated(id=record.id, status=JobState.PENDING)

    @app.post(
        "/api/jobs/batch",
        response_model=JobCreated,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
    )
    def batch_endpoint(request: BatchRequest, manager: JobManager = Depends(get_manager)) -> JobCreated:
        try:
            record = manager.batch(request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return JobCreated(id=record.id, status=JobState.PENDING)

    @app.get(
        "/api/jobs/{job_id}",
        response_model=JobDetail,
        dependencies=[Depends(require_token)],
    )
    def job_detail(job_id: str, manager: JobManager = Depends(get_manager)) -> JobDetail:
        try:
            record = manager.get(job_id)
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
        return record.to_detail()

    @app.get(
        "/api/jobs/{job_id}/logs",
        dependencies=[Depends(require_token)],
    )
    def job_logs(job_id: str, manager: JobManager = Depends(get_manager)) -> Any:
        try:
            logs = manager.iter_logs(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc

        log_models: List[JobLogEntryModel] = [entry.to_model() for entry in logs]

        def _iter() -> Iterator[str]:
            for entry in log_models:
                yield json.dumps(entry.model_dump(), ensure_ascii=False) + "\n"

        return StreamingResponse(_iter(), media_type="application/x-ndjson")

    @app.delete(
        "/api/jobs/{job_id}",
        response_class=Response,
        status_code=status.HTTP_204_NO_CONTENT,
        response_model=None,
        dependencies=[Depends(require_token)],
    )
    def cancel_job(job_id: str, manager: JobManager = Depends(get_manager)) -> Any:
        try:
            record = manager.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
        cancelled = manager.cancel(job_id)
        if not cancelled and record.status not in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job is already running and could not be cancelled.",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


__all__ = ["create_app"]
