"""Pydantic models for the control surface service."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class JobState(str, Enum):
    """Lifecycle states for asynchronous jobs."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunCsvRequest(BaseModel):
    """Request payload for launching a ``run-csv`` job."""

    csv: str = Field(..., description="CSV workload to replay.")
    mode: str = Field(default="adaptive", description="Hash map backend/mode to execute with.")
    metrics_port: Optional[int] = Field(
        default=None, description="Optional metrics/dashboard port (set 0 for ephemeral)."
    )
    metrics_host: Optional[str] = Field(
        default=None,
        description="Optional host/interface override for metrics server (defaults to ADHASH_METRICS_HOST or 127.0.0.1).",
    )
    snapshot_in: Optional[str] = Field(
        default=None, description="Existing snapshot to resume from."
    )
    snapshot_out: Optional[str] = Field(
        default=None,
        description="Snapshot path to write on completion (auto gzip by suffix or --compress).",
    )
    compress_out: bool = Field(
        default=False, description="Enable gzip compression for snapshot writes."
    )
    compact_interval: Optional[float] = Field(
        default=None, description="Seconds between proactive compactions (None disables)."
    )
    json_summary_out: Optional[str] = Field(
        default=None, description="Optional JSON summary output path for CI/reporting."
    )
    latency_sample_k: int = Field(
        default=1000, ge=0, description="Reservoir size for latency sampling."
    )
    latency_sample_every: int = Field(
        default=128, ge=1, description="Sample every Nth operation for latency calculations."
    )
    latency_bucket_preset: str = Field(
        default="default",
        description="Latency histogram preset identifier (see docs/metrics_schema.md).",
    )
    metrics_out_dir: Optional[str] = Field(
        default=None, description="Directory where metrics.ndjson should be written."
    )
    metrics_max_ticks: Optional[int] = Field(
        default=None, description="Retention cap for metrics.ndjson when running with --follow."
    )
    dry_run: bool = Field(
        default=False,
        description="Validate the workload without executing operations (ensures CSV schema compliance).",
    )
    csv_max_rows: int = Field(
        default=5_000_000,
        ge=0,
        description="Abort if CSV exceeds this many rows (0 disables the guard).",
    )
    csv_max_bytes: int = Field(
        default=500 * 1024 * 1024,
        ge=0,
        description="Abort if CSV exceeds this many bytes (0 disables the guard).",
    )
    metrics_host_env_fallback: bool = Field(
        default=True,
        description="When true, fall back to ADHASH_METRICS_HOST env var for metrics host binding.",
    )
    capture_history: bool = Field(
        default=False,
        description="Populate the in-memory metrics history buffer (used for A/B comparisons).",
    )
    working_dir: Optional[str] = Field(
        default=None,
        description="Override working directory for this job (defaults to current process CWD).",
    )

    @field_validator("csv", "mode")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class ProfileRequest(BaseModel):
    """Request payload for running the workload profiler."""

    csv: str = Field(..., description="CSV workload to profile.")
    sample_limit: int = Field(
        default=5000,
        gt=0,
        description="Sample size when determining the recommended backend/mode.",
    )
    working_dir: Optional[str] = Field(
        default=None,
        description="Override working directory for this job (defaults to current process CWD).",
    )

    @field_validator("csv")
    @classmethod
    def _csv_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("csv must not be blank")
        return value


class BatchRequest(BaseModel):
    """Launch a batch spec leveraging the existing batch runner."""

    spec_path: str = Field(..., description="Path to a batch TOML spec.")
    working_dir: Optional[str] = Field(
        default=None,
        description="Optional working directory passed to the batch runner.",
    )

    @field_validator("spec_path")
    @classmethod
    def _spec_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("spec_path must not be blank")
        return value


class JobLogEntryModel(BaseModel):
    """Structured representation of a captured log line."""

    timestamp: float = Field(..., description="Unix timestamp for the log entry.")
    level: str = Field(..., description="Logging level name (INFO/ERROR/etc.).")
    message: str = Field(..., description="Log message text.")


class JobCreated(BaseModel):
    """Response returned immediately after a job is accepted."""

    id: str = Field(..., description="Server-generated job identifier.")
    status: JobState = Field(..., description="Initial job state (pending until worker starts).")


class JobDetail(BaseModel):
    """Full job metadata surfaced over the REST API."""

    id: str
    kind: str
    status: JobState
    created_at: float
    updated_at: float
    request: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Lightweight summary for listing jobs."""

    jobs: List[JobDetail]
