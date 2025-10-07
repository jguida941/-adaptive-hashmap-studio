# Operations Runbook

This runbook captures the day-to-day operational tasks for Adaptive Hash Map CLI deployments, the Mission Control UI, and release hygiene. Use it as the primary reference for on-call engineers and release managers.

## 1. Environment Preparation

- **Python runtime**: 3.11 or 3.12 with the `dev` extras installed (`pip install -e '.[dev]'`).
- **Optional UI dependencies**: install `.[gui]` for PyQt6/pyqtgraph widgets and `.[ui]` for the Textual TUI when interactive tooling is required.
- **Optional service dependencies**: install `.[service]` to run the FastAPI control surface (`python -m adhash.service`).
- **Environment variables**:
  - `ADHASH_TOKEN` – bearer token for securing `/api/*` endpoints and Mission Control.
  - `ADHASH_METRICS_PORT` – override default 9090 when running multiple instances.
  - `ADHASH_PRESETS_DIR` – directory for Mission Control config presets.
- **Off-screen rendering**: set `QT_QPA_PLATFORM=offscreen` in headless CI/automation runs involving Mission Control widgets.

## 2. Smoke Validation Checklist

Run the following after every deploy, configuration change, or release cut:

```bash
make smoke
```

This target generates a synthetic workload, replays it with the adaptive map, and validates the emitted `metrics.ndjson` against `metrics.v1`. Inspect `runs/metrics.ndjson` if the validator reports errors.

Additional ad-hoc checks:

1. **CLI contract tests** – `pytest tests/test_cli_contracts.py -q`
2. **Probe tooling** – `pytest tests/test_cli_probe_command.py tests/test_tui_probe.py -q`
3. **Mission Control widgets (optional)** – ensure PyQt6 is available, then run `pytest tests/test_mission_control_widgets_qt.py -q`

## 3. Mission Control Deployment

1. Launch the metrics server: `python -m hashmap_cli serve --host 0.0.0.0 --port $ADHASH_METRICS_PORT`
2. Start Mission Control: `python -m adhash.mission_control.app`
3. Verify tabs:
   - Metrics pane updating live ticks
   - Probe Visualizer tab loads a JSON trace exported via `hashmap-cli probe-visualize --export-json`
   - Snapshot Inspector can open a `.pkl/.pkl.gz` snapshot
4. Authentication: ensure `ADHASH_TOKEN` is set in both the server and Mission Control environment.
5. Logs: Mission Control writes rotating JSON logs to `~/.cache/adhash/mission_control.log`. Retain the last 7 files.

## 4. Textual TUI Deployment

- Launch via `python -m adhash.tui --metrics-endpoint http://host:port/api/metrics --probe-json trace.json`
- Key bindings: `r` refresh, `p` reload probe, `q` quit
- Ensure probe trace reloads after re-export from the CLI; the pane should display the active path and metadata.

## 5. Control Surface Service

- Install service extras (`pip install -e '.[service]'`) and ensure FastAPI/uvicorn are available.
- Launch the REST control surface: `python -m adhash.service --host 0.0.0.0 --port 9600 --job-root runs/jobs`.
- Environment knobs:
  - `ADHASH_JOB_ROOT` – default directory for job metadata, logs, and artifacts (`runs/jobs` if unset).
  - `ADHASH_MAX_JOBS` – cap concurrent jobs; overrides `--max-jobs` when provided.
- Health checks: `curl http://127.0.0.1:9600/healthz` and `curl http://127.0.0.1:9600/api/jobs`.
- Submit a dry-run smoke test:
  ```bash
  curl -X POST http://127.0.0.1:9600/api/jobs/run-csv \
       -H 'Content-Type: application/json' \
       -d '{"csv": "data/workloads/demo.csv", "mode": "adaptive", "dry_run": true}'
  ```
  Poll `GET /api/jobs/<id>` until status reaches `completed`; artifacts and logs appear under `$ADHASH_JOB_ROOT/<id>/`.
- Logs: `logs.ndjson` in the job directory captures combined stdout/stderr and logger output. Stream live logs via `curl --no-buffer http://127.0.0.1:9600/api/jobs/<id>/logs`.

## 6. Release Procedure

1. Bump the version in `pyproject.toml`, add a Towncrier fragment under `newsfragments/`, and update roadmap docs as needed.
2. Run `make release` locally. The target will:
   - Build `docs/CHANGELOG.md` from Towncrier fragments, skipping the step if no fragment exists.
   - Generate sdists/wheels plus `SHA256SUMS.txt` and `source-sbom.spdx.json` under `dist/`.
   - Execute `twine check` against the artifacts.
   Validate locally before tagging:
   - `shasum -a 256 --check dist/SHA256SUMS.txt` (or `sha256sum --check`).
   - `jq '.artifacts' dist/source-sbom.spdx.json` to review the SBOM envelope.
3. Publish to Python Package Indexes:
   - Export `TWINE_USERNAME=__token__` and the appropriate `TWINE_PASSWORD` or `PYPI_API_TOKEN` in your shell (tokens live in 1Password).
   - `make publish-testpypi` for a rehearsal push (`--skip-existing` keeps re-runs idempotent).
   - After validating the TestPyPI page, re-run `make release` if fragments changed, then execute `make publish-pypi`.
4. Tag the release (`git tag vX.Y.Z && git push origin vX.Y.Z`). The `release.yml` workflow will rerun lint/type/tests, build artifacts, attach SBOM/checksums, upload to TestPyPI/PyPI when secrets are configured, and push Docker images with provenance metadata.
5. Refresh the Homebrew tap (manual step until automation is online):
   - Update the formula repo checkout (e.g., `adaptive-hashmap/homebrew-adhash`).
   - Compute the new tarball checksum: `shasum -a 256 dist/adaptive-hashmap-cli-<VERSION>.tar.gz`.
   - Run `brew bump-formula-pr --strict --url "https://files.pythonhosted.org/packages/.../adaptive_hashmap_cli-<VERSION>.tar.gz" --sha256 <CHECKSUM>` (replace the URL with the exact path from the PyPI release page).
   - Inspect the generated PR, ensure the binary runs via `brew test --verbose adaptive-hashmap-cli`, then merge.
6. Verify artifacts from the CI run (download `SHA256SUMS.txt`, inspect the SBOM, and spot-check the container via `hashmap-cli --help`).
7. Publish release notes referencing the generated Towncrier section and highlight any schema/backward compatibility changes.

## 7. Incident Response

- **Metrics server down**: restart the `hashmap-cli serve` process and review logs under `~/.cache/adhash/metrics.log`
- **Mission Control freeze**: restart the Qt application; if reproducible, capture the `mission_control.log` and a screen recording.
- **Probe trace errors**: ensure trace JSON matches `format_trace_lines` expectations (`schema`, `trace`, `seed_entries` fields) and re-export from the CLI.
- **Snapshot failures**: run `python -m hashmap_cli verify-snapshot --in SNAPSHOT.pkl.gz --json` and examine the error envelope (`BadInput` vs `Invariant`).

## 8. Service Levels

- **Metrics availability**: `/api/metrics` and `/metrics` should respond within 500 ms for 99% of requests over rolling 5-minute windows. Escalate if latency breaches this window or error rate exceeds 1%.
- **Mission Control responsiveness**: dashboard must render within 3 s on reference hardware (Apple M2, 16 GB RAM). Restart and capture logs if launch time regresses.
- **Validation cadence**: block releases until `make smoke` and `pytest -q` succeed; record evidence in `audit.md` during cutover.

## 9. Runbook Maintenance

- Update this document when new CLI flags, UI panels, or release steps are introduced.
- Link new operational scripts or dashboards here and in `README.md` so they remain discoverable.
