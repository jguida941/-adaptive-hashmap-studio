"""Job orchestration utilities for the control surface service."""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
import traceback
import uuid
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple, TextIO

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor

from adhash.batch.runner import BatchRunner, JobResult, load_spec
from adhash.hashmap_cli import profile_csv, run_csv

from .models import (
    BatchRequest,
    JobDetail,
    JobLogEntryModel,
    JobState,
    ProfileRequest,
    RunCsvRequest,
)
from .worker import JobWorker

logger = logging.getLogger(__name__)

_DEFAULT_JOB_ROOT = "runs/jobs"
_DEFAULT_MAX_WORKERS = 4
_LOG_LIMIT = 2000


@dataclass
class JobLogEntry:
    """Internal representation of a streamed log entry."""

    timestamp: float
    level: str
    message: str

    def to_model(self) -> JobLogEntryModel:
        return JobLogEntryModel(timestamp=self.timestamp, level=self.level, message=self.message)


@dataclass
class JobRecord:
    """Mutable record stored for every job managed by the service."""

    id: str
    kind: str
    status: JobState
    request: Dict[str, Any]
    created_at: float
    updated_at: float
    path: Path
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    logs: List[JobLogEntry] = field(default_factory=list)

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


class JobManager:
    """Coordinates asynchronous CLI jobs for the control surface."""

    def __init__(
        self,
        base_dir: Optional[str | Path] = None,
        *,
        max_workers: Optional[int] = None,
    ) -> None:
        env_root = os.getenv("ADHASH_JOB_ROOT")
        resolved_base = Path(base_dir or env_root or _DEFAULT_JOB_ROOT).expanduser().resolve()
        resolved_base.mkdir(parents=True, exist_ok=True)
        self.base_dir = resolved_base
        if max_workers is None:
            env_workers = os.getenv("ADHASH_MAX_JOBS")
            if env_workers:
                try:
                    max_workers = max(1, int(env_workers))
                except ValueError:
                    logger.warning(
                        "Invalid ADHASH_MAX_JOBS value '%s'; defaulting to %s",
                        env_workers,
                        _DEFAULT_MAX_WORKERS,
                    )
                    max_workers = _DEFAULT_MAX_WORKERS
            else:
                max_workers = _DEFAULT_MAX_WORKERS
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.RLock()
        self._jobs: Dict[str, JobRecord] = {}
        self._futures: Dict[str, Future[Any]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        """Shut down the underlying executor."""
        self._executor.shutdown(wait=True, cancel_futures=False)

    def run_csv(self, request: RunCsvRequest) -> JobRecord:
        """Schedule a ``run-csv`` job."""
        record = self._create_job("run-csv", request.model_dump())
        worker = JobWorker(
            job_id=record.id,
            manager=self,
            description=f"run-csv {request.csv}",
            target=self._execute_run_csv,
            args=(record.id, request),
        )
        self._submit(record, worker)
        return self.get(record.id)

    def profile(self, request: ProfileRequest) -> JobRecord:
        """Schedule a workload ``profile`` job."""
        record = self._create_job("profile", request.model_dump())
        worker = JobWorker(
            job_id=record.id,
            manager=self,
            description=f"profile {request.csv}",
            target=self._execute_profile,
            args=(record.id, request),
        )
        self._submit(record, worker)
        return self.get(record.id)

    def batch(self, request: BatchRequest) -> JobRecord:
        """Schedule a batch suite job."""
        record = self._create_job("batch", request.model_dump())
        worker = JobWorker(
            job_id=record.id,
            manager=self,
            description=f"batch {request.spec_path}",
            target=self._execute_batch,
            args=(record.id, request),
        )
        self._submit(record, worker)
        return self.get(record.id)

    def get(self, job_id: str) -> JobRecord:
        """Retrieve the job record (raises KeyError if unknown)."""
        with self._lock:
            record = self._jobs[job_id]
            return record

    def list(self) -> List[JobRecord]:
        """Return all jobs sorted by creation time (most recent last)."""
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at)

    def iter_logs(self, job_id: str) -> Iterable[JobLogEntry]:
        """Yield captured log entries for a job."""
        with self._lock:
            record = self._jobs[job_id]
            return list(record.logs)

    def wait(self, job_id: str, timeout: Optional[float] = None) -> JobRecord:
        """Block until a job finishes (completed or failed)."""
        future = self._futures.get(job_id)
        if future is None:
            # Already finished or unknown
            return self.get(job_id)
        try:
            future.result(timeout=timeout)
        except CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - exception already recorded
            logger.debug("Job %s raised %s during wait", job_id, exc)
        return self.get(job_id)

    def cancel(self, job_id: str) -> bool:
        """Attempt to cancel a pending job. Returns True if cancellation succeeded."""
        with self._lock:
            future = self._futures.get(job_id)
        if future is None:
            return False
        cancelled = future.cancel()
        if cancelled:
            with self._lock:
                record = self._jobs[job_id]
                record.status = JobState.CANCELLED
                record.updated_at = time.time()
                self._write_status(record)
            self._append_log(job_id, "Job cancelled.", "WARNING")
        return cancelled

    # ------------------------------------------------------------------
    # Internal helpers used by JobWorker
    # ------------------------------------------------------------------
    def _mark_running(self, job_id: str) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = JobState.RUNNING
            record.updated_at = time.time()
            self._write_status(record)

    def _mark_completed(
        self, job_id: str, result: Dict[str, Any], artifacts: Dict[str, str]
    ) -> None:
        with self._lock:
            record = self._jobs[job_id]
            record.status = JobState.COMPLETED
            record.updated_at = time.time()
            record.result = result
            if artifacts:
                record.artifacts.update(artifacts)
            self._write_status(record)
        self._write_result(job_id, result)
        if artifacts:
            self._write_artifacts(job_id, artifacts)
        self._append_log(job_id, "Job completed successfully.", "INFO")

    def _mark_failed(self, job_id: str, exc: BaseException) -> None:
        formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with self._lock:
            record = self._jobs[job_id]
            record.status = JobState.FAILED
            record.updated_at = time.time()
            record.error = formatted
            self._write_status(record)
        self._write_error(job_id, formatted)
        self._append_log(job_id, f"Job failed: {exc}", "ERROR")

    @contextmanager
    def _capture_output(self, job_id: str) -> Iterator[None]:
        """Capture stdout/stderr and logging output for the given job."""

        class _Handler(logging.Handler):
            def __init__(self, hook: Callable[[str, str], None]) -> None:
                super().__init__()
                self._hook = hook

            def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
                try:
                    msg = self.format(record)
                except Exception:  # pragma: no cover - defensive
                    msg = record.getMessage()
                self._hook(msg, record.levelname)

        class _ThreadFilter(logging.Filter):
            def __init__(self, thread_id: int) -> None:
                super().__init__()
                self._thread_id = thread_id

            def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
                return record.thread == self._thread_id

        handler = _Handler(lambda msg, level: self._append_log(job_id, msg, level))
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        handler.addFilter(_ThreadFilter(threading.get_ident()))

        root_logger = logging.getLogger()
        cli_logger = logging.getLogger("hashmap_cli")
        root_logger.addHandler(handler)
        cli_logger.addHandler(handler)

        stream = _LogStream(lambda text: self._append_log(job_id, text, "INFO"))

        overridden_streams: List[Tuple[logging.StreamHandler, TextIO]] = []

        def _restore_stream(log_handler: logging.StreamHandler, original_stream: TextIO) -> None:
            log_handler.setStream(original_stream)

        for log_handler in list(cli_logger.handlers):
            if log_handler is handler:
                continue
            if isinstance(log_handler, logging.StreamHandler):
                original_stream = log_handler.stream
                overridden_streams.append((log_handler, original_stream))
                log_handler.setStream(stream)

        with ExitStack() as stack:
            stack.callback(root_logger.removeHandler, handler)
            stack.callback(cli_logger.removeHandler, handler)
            for log_handler, original_stream in overridden_streams:
                stack.callback(_restore_stream, log_handler, original_stream)
            stack.enter_context(redirect_stdout(stream))
            stack.enter_context(redirect_stderr(stream))
            try:
                yield
            finally:
                stream.flush()

    # ------------------------------------------------------------------
    # Worker targets
    # ------------------------------------------------------------------
    def _execute_run_csv(
        self, job_id: str, request: RunCsvRequest
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        working_dir = (
            Path(request.working_dir).expanduser().resolve() if request.working_dir else None
        )
        csv_arg = self._prepare_path(request.csv, working_dir)
        snapshot_in = self._prepare_optional_path(request.snapshot_in, working_dir)
        snapshot_out = self._prepare_optional_path(request.snapshot_out, working_dir)
        metrics_out_dir = self._prepare_optional_path(request.metrics_out_dir, working_dir)
        json_summary_out = self._prepare_optional_path(request.json_summary_out, working_dir)

        metrics_host = request.metrics_host
        if metrics_host is None and not request.metrics_host_env_fallback:
            metrics_host = "127.0.0.1"

        kwargs: Dict[str, Any] = {
            "metrics_port": request.metrics_port,
            "snapshot_in": snapshot_in,
            "snapshot_out": snapshot_out,
            "compress_out": request.compress_out,
            "compact_interval": request.compact_interval,
            "json_summary_out": json_summary_out,
            "latency_sample_k": request.latency_sample_k,
            "latency_sample_every": request.latency_sample_every,
            "latency_bucket_preset": request.latency_bucket_preset,
            "metrics_out_dir": metrics_out_dir,
            "metrics_max_ticks": request.metrics_max_ticks,
            "dry_run": request.dry_run,
            "csv_max_rows": request.csv_max_rows,
            "csv_max_bytes": request.csv_max_bytes,
            "metrics_host": metrics_host,
            "capture_history": request.capture_history,
        }

        with self._use_working_dir(working_dir), self._capture_output(job_id):
            result = run_csv(
                csv_arg,
                request.mode,
                **kwargs,
            )

        artifacts: Dict[str, str] = {}
        for key, value in (
            ("snapshot_out", snapshot_out),
            ("json_summary_out", json_summary_out),
            ("metrics_out_dir", metrics_out_dir),
        ):
            if value:
                artifacts[key] = value

        return result, artifacts

    def _execute_profile(
        self, job_id: str, request: ProfileRequest
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        working_dir = (
            Path(request.working_dir).expanduser().resolve() if request.working_dir else None
        )
        csv_arg = self._prepare_path(request.csv, working_dir)

        with self._use_working_dir(working_dir), self._capture_output(job_id):
            recommended = profile_csv(csv_arg, sample_limit=request.sample_limit)

        result = {
            "status": "completed",
            "csv": csv_arg,
            "recommended_mode": recommended,
            "sample_limit": request.sample_limit,
        }
        return result, {}

    def _execute_batch(
        self, job_id: str, request: BatchRequest
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        working_dir = (
            Path(request.working_dir).expanduser().resolve() if request.working_dir else None
        )
        spec_path = self._prepare_path(request.spec_path, working_dir)

        with self._use_working_dir(working_dir), self._capture_output(job_id):
            spec = load_spec(Path(spec_path))
            runner = BatchRunner(spec)
            results = runner.run()

        serialized = [_serialize_batch_result(item) for item in results]
        result = {
            "status": "completed",
            "spec": spec_path,
            "jobs": serialized,
            "report": str(spec.report_path),
            "html_report": str(spec.html_report_path) if spec.html_report_path else None,
        }
        artifacts: Dict[str, str] = {"report": str(spec.report_path)}
        if spec.html_report_path:
            artifacts["html_report"] = str(spec.html_report_path)
        return result, artifacts

    # ------------------------------------------------------------------
    # Private utilities
    # ------------------------------------------------------------------
    def _create_job(self, kind: str, payload: Dict[str, Any]) -> JobRecord:
        job_id = uuid.uuid4().hex
        now = time.time()
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        record = JobRecord(
            id=job_id,
            kind=kind,
            status=JobState.PENDING,
            request=payload,
            created_at=now,
            updated_at=now,
            path=job_dir,
        )
        with self._lock:
            self._jobs[job_id] = record
        self._write_request(job_id, payload)
        self._write_status(record)
        return record

    def _submit(self, record: JobRecord, worker: JobWorker) -> None:
        future = self._executor.submit(worker)

        def _cleanup(fut: Future[Any]) -> None:
            try:
                exc = fut.exception()
            except CancelledError:
                exc = None
            except Exception as err:  # pragma: no cover - defensive
                logger.debug("Job %s raised %s", record.id, err)
                exc = err
            if exc:
                logger.debug("Job %s raised %s", record.id, exc)
            with self._lock:
                self._futures.pop(record.id, None)

        with self._lock:
            self._futures[record.id] = future
            future.add_done_callback(_cleanup)

    def _append_log(self, job_id: str, message: str, level: str) -> None:
        message = message.rstrip()
        if not message:
            return
        timestamp = time.time()
        entry = JobLogEntry(timestamp=timestamp, level=level, message=message)
        with self._lock:
            record = self._jobs[job_id]
            record.logs.append(entry)
            record.updated_at = timestamp
            if len(record.logs) > _LOG_LIMIT:
                record.logs = record.logs[-_LOG_LIMIT:]
        log_path = self.base_dir / job_id / "logs.ndjson"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"ts": timestamp, "level": level, "message": message}, ensure_ascii=False
                )
                + "\n"
            )

    def _write_request(self, job_id: str, payload: Dict[str, Any]) -> None:
        self._write_json(self.base_dir / job_id / "request.json", payload)

    def _write_result(self, job_id: str, payload: Dict[str, Any]) -> None:
        self._write_json(self.base_dir / job_id / "result.json", payload)

    def _write_status(self, record: JobRecord) -> None:
        payload = {
            "id": record.id,
            "status": record.status.value,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
        self._write_json(record.path / "status.json", payload)

    def _write_artifacts(self, job_id: str, artifacts: Dict[str, str]) -> None:
        self._write_json(self.base_dir / job_id / "artifacts.json", artifacts)

    def _write_error(self, job_id: str, text: str) -> None:
        error_path = self.base_dir / job_id / "error.txt"
        error_path.write_text(text, encoding="utf-8")

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _prepare_path(path_str: str, working_dir: Optional[Path]) -> str:
        path = Path(path_str)
        path = path.expanduser()
        if path.is_absolute():
            return str(path.resolve())
        if working_dir is not None:
            return str((working_dir / path).resolve())
        return str(path.resolve())

    @staticmethod
    def _prepare_optional_path(
        path_str: Optional[str], working_dir: Optional[Path]
    ) -> Optional[str]:
        if path_str is None:
            return None
        return JobManager._prepare_path(path_str, working_dir)

    @contextmanager
    def _use_working_dir(self, working_dir: Optional[Path]) -> Iterator[None]:
        if working_dir is None:
            yield
            return
        working_dir.mkdir(parents=True, exist_ok=True)
        yield


def _serialize_batch_result(result: JobResult) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": result.spec.name,
        "command": result.spec.command,
        "csv": str(result.spec.csv),
        "mode": result.spec.mode,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.summary is not None:
        payload["summary"] = result.summary
    return payload


class _LogStream(io.StringIO):
    """File-like wrapper that forwards writes into the job log stream."""

    def __init__(self, hook: Callable[[str], None]) -> None:
        super().__init__()
        self._hook = hook
        self._buffer = ""

    def write(self, data: str) -> int:
        if not data:
            return 0
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip("\r")
            if line:
                self._hook(line)
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            remainder = self._buffer.rstrip("\r")
            if remainder:
                self._hook(remainder)
            self._buffer = ""
        super().flush()


__all__ = ["JobManager", "JobRecord", "JobLogEntry"]
