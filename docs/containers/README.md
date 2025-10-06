# Containers & Deployment

This project now ships with container images and supporting automation so the CLI, metrics server, and batch workloads can run in orchestrated environments.

## Images

| Dockerfile | Purpose | Notes |
| --- | --- | --- |
| `docker/Dockerfile` | Production image with non-root user, curl-based health check, and configurable ports. | Built via `make docker-build` and used by CI release workflows. |
| `docker/Dockerfile.dev` | Developer image with `.[dev]` extras installed for lint/type/test loops. | Ideal for VS Code Dev Containers or remote runners. |

Both images honour the entrypoint script at `docker/entrypoint.sh`, which injects sensible defaults for `serve` and `run-csv` when `ADHASH_METRICS_HOST` / `ADHASH_METRICS_PORT` are set.

## Build & Run

```bash
# Build the production image locally
make docker-build

# Start the metrics dashboard (binds 0.0.0.0:${ADHASH_METRICS_PORT:-9090})
docker run --rm \
  -p ${ADHASH_METRICS_PORT:-9090}:${ADHASH_METRICS_PORT:-9090} \
  -e ADHASH_METRICS_PORT=${ADHASH_METRICS_PORT:-9090} \
  adaptive-hashmap-cli:local serve

# Replay a workload and stream metrics back to the same container
mkdir -p snapshots
cp data/workloads/w_uniform.csv snapshots/
docker run --rm \
  -v "$(pwd)/snapshots:/snapshots" \
  adaptive-hashmap-cli:local run-csv \
    --csv /snapshots/w_uniform.csv \
    --metrics-port ${ADHASH_METRICS_PORT:-9090} \
    --metrics-host host.docker.internal \
    --metrics-out-dir /snapshots/metrics

# Tip: substitute `--metrics-port auto` (or `ADHASH_METRICS_PORT=auto`) to let the OS pick an available port; the CLI prints the bound value once the server starts.
```

## docker-compose

`docker/docker-compose.yml` wires two services together:

- `mission-control`: long-running metrics/dashboard endpoint with health check.
- `workload-runner`: one-shot replay that pushes ticks to the mission-control service and drops NDJSON under `./snapshots`.

Bring the stack up with:

```bash
docker compose -f docker/docker-compose.yml up --build
```

Override workload paths or ports by exporting `ADHASH_METRICS_PORT`, `ADHASH_TOKEN`, or editing the command array.

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `ADHASH_METRICS_PORT` | `9090` | Port exposed by `serve` and `run-csv --metrics-port`. Set to `auto` to bind an ephemeral port (the CLI logs the chosen value). |
| `ADHASH_METRICS_HOST` | `0.0.0.0` in containers, `127.0.0.1` elsewhere | Bind interface for metrics server. |
| `ADHASH_TOKEN` | empty | Auth token enforced by Mission Control/dashboard clients (set to require `Authorization: Bearer`). |
| `ADHASH_CONFIG` | unset | Optional path to load a TOML config inside the container. |

## Health & Observability

- Liveness/Readiness: the image exposes `/healthz` and `/readyz`, polled via `curl` in the Dockerfile health check.
- Prometheus: scrape `/metrics` (plain-text) or `/api/metrics` (JSON) once the container is running.
- NDJSON: mount a writable directory and pass `--metrics-out-dir /mount/path` to capture history.

## Release Pipeline Hooks

The GitHub Actions release workflow (introduced in Phase 3) builds this Docker image, pushes it to GHCR with provenance/SBOM metadata, and attaches the wheel/sdist artefacts to GitHub Releases. Local builds created via `make docker-build` mirror the same layout, so pre-release validation matches CI results.

## Developer Image

For iterative work inside a container:

```bash
make docker-build-dev
docker run --rm -it -v "$(pwd):/workspace" adaptive-hashmap-cli:dev bash
```

This image pre-installs `.[dev]` dependencies, so `ruff`, `mypy`, `pytest`, and `textual` tooling are immediately available.
