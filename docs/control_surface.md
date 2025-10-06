# External Control Surface Design

## Goals

- Allow automation frameworks and external services to trigger Adaptive Hash Map workloads programmatically (no shelling out to the CLI).
- Provide a stable contract for launching `run-csv`, `profile`, batch suites, and ad-hoc probe traces.
- Expose job status, logs, metrics endpoints, and artifacts (snapshots, JSON summaries) via HTTP APIs guarded by the same auth story as Mission Control (`ADHASH_TOKEN`).
- Keep the implementation modular so both REST requests and in-process Python callers share the same orchestration layer.

## Chosen Approach

We will build a lightweight REST service backed by FastAPI/uvicorn. REST is preferred over gRPC for the first iteration because:

- The project already exposes HTTP/JSON metrics; reusing that stack simplifies deployment and documentation.
- FastAPI integrates cleanly with Pydantic models, letting us reuse existing `config_models` schemas and validation helpers.
- Mission Control and other tools can consume REST endpoints without new client libraries.

The service will live under a new module namespace: `src/adhash/service/`.

```
src/adhash/service/
├── __init__.py
├── api.py          # FastAPI router definitions
├── jobs.py         # orchestration layer shared by REST + Python bindings
├── models.py       # Pydantic request/response schemas
└── worker.py       # background execution + subprocess management
```

A thin CLI entry point (`python -m adhash.service`) will start the server and expose a simple client for embedded use (`adhash.service.client`).

## High-Level Flow

1. REST client issues `POST /api/jobs/run-csv` with workload parameters (CSV path, presets, metrics settings).
2. `jobs.JobManager` validates the request, creates a job record, and enqueues work on a thread/async worker.
3. `worker.JobWorker` executes the job via in-process functions (prefer `adhash.batch.runner` and `hashmap_cli` helpers) and captures stdout/stderr incrementally.
4. Job state transitions through `pending → running → completed/failed`. Artifacts (JSON summaries, NDJSON, snapshots) are registered in the job record.
5. REST clients poll `GET /api/jobs/{job_id}` or subscribe to `GET /api/jobs/{job_id}/events` (Server-Sent Events) for progress. Metrics streams continue to go through the existing metrics server.

## API Surface (v0)

| Method & Path | Description | Request Model | Response Model |
| --- | --- | --- | --- |
| `POST /api/jobs/run-csv` | Launch `run-csv` with optional config, metrics, and snapshot args. | `RunCsvRequest` (extends existing CLI flags) | `JobCreated` (id + initial status). |
| `POST /api/jobs/profile` | Trigger `profile` for a CSV. | `ProfileRequest` | `JobCreated`. |
| `POST /api/jobs/batch` | Execute a batch spec (`BatchSpec` schema). | `BatchRequest` | `JobCreated`. |
| `GET /api/jobs/{id}` | Fetch job metadata, parameters, status timeline, artifacts. | – | `JobDetail`. |
| `GET /api/jobs/{id}/logs` | Stream stdout/stderr tail. Supports `?since=` tokens. | – | NDJSON stream. |
| `DELETE /api/jobs/{id}` | Cancel an active job (or delete artifacts for terminal jobs). | – | `JobDetail` (final state). |

Future extensions (backlog):

- `POST /api/jobs/verify-snapshot`
- `POST /api/jobs/probe-visualize`
- WebSocket or SSE channel for Mission Control to subscribe to job events directly.

## Authentication & Authorization

- Reuse `ADHASH_TOKEN` for bearer auth (same as metrics dashboard). The FastAPI dependency will verify the header or `?token=` query parameter.
- Support optional mTLS or reverse-proxy termination in front of the service. No direct TLS for the first iteration.

## Artifact Handling

- Jobs write artifacts to a configurable base directory (`ADHASH_JOB_ROOT`, default `runs/jobs/`).
- Each job gets a subdirectory containing:
  - Raw stdout/stderr logs
  - Serialized job spec
  - JSON summaries / metrics ndjson / snapshots (symlinks to existing paths when produced by CLI helpers)
- `GET /api/jobs/{id}/artifacts/{name}` will expose signed URLs (using `itsdangerous`) for time-limited download.

## Python Bindings

Provide a thin Python interface so orchestrators can embed the control surface without HTTP:

```python
from adhash.service.jobs import JobManager

manager = JobManager(base_dir=Path("runs/jobs"))
job = manager.run_csv(csv="data/demo.csv", config="config.toml", metrics_port="auto")
while not job.is_finished:
    job.poll()
summary = job.read_summary()
```

Bindings internally call the same `JobManager` used by REST routes to avoid divergence.

## Testing Strategy

- Unit tests for `JobManager` and `JobWorker` to validate state transitions, failure modes, and artifact registration.
- FastAPI integration tests using `httpx.AsyncClient` to exercise the routes (`tests/test_service_api.py`).
- Contract tests that run against a temporary job root and assert log/summary contents for `run-csv` and `profile` jobs.
- Cancellation tests: start a long-running job, issue `DELETE`, ensure process termination and cleanup.
- Security tests: missing/invalid token returns 401, CORS headers align with metrics server defaults.

## Observability

- Leverage existing logging setup; emit structured job events (JSON) with job id, phase, duration, exit code.
- Expose Prometheus counters (`adhash_jobs_total`, `adhash_jobs_running`) through the metrics server by registering a shared metrics collector.

## Open Questions

- How should we sandbox jobs (especially when running untrusted CSVs)? Consider optional process isolation via subprocess + seccomp profile in Phase 3.
- Do we need multi-tenant quotas (max concurrent jobs per token)? For now we will enforce a global `MAX_CONCURRENT_JOBS` (configurable via env).
- Should Mission Control embed the REST client or call the Python bindings directly? Initial plan: Mission Control talks to REST so remote instances work out of the box.

## Deliverables

1. New `adhash.service` package with FastAPI app, job manager, schemas, and CLI entry point.
2. Automated tests as described above plus documentation under `docs/control_surface.md` (this document) and README/upgrade updates.
3. Runbook updates covering service deployment and integration with Mission Control/TUI.
4. Follow-up issue: evaluate gRPC or CLI plugin once REST API stabilizes and user demand is clearer.
