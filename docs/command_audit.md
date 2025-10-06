# Command Audit & Verification Checklist

Status legend:

- ✅ Verified – executed recently and confirmed working (noting whether automated or manual).
- 🟡 Pending – requires a manual run (not yet exercised after the latest changes).
- 🔄 Covered by automated tests – exercised indirectly via lint/type/unit suites.

Where commands depend on extras, the required install flags are noted. All paths are relative to the repo root.

## Core CLI Surface

| Status | Command | Notes / Preconditions | Source |
|--------|---------|-----------------------|--------|
| 🟡 Pending | `python -m hashmap_cli -h` | Ensure general help renders without tracebacks. | README |
| ✅ Verified (scripted) | `python -m hashmap_cli config-wizard --outfile config/config.toml` | 2025-10-03: Scripted Enter defaults to regenerate `config/config.toml` after modularisation. | `src/adaptive_hashmap_cli.egg-info/PKG-INFO` |
| ✅ Verified (manual) | `python -m hashmap_cli config-edit --infile config/config.toml --outfile runs/oct3_config_edit.toml --save-preset demo --presets-dir runs/presets --force` | 2025-10-04: Edited default file, saved preset to `runs/presets/demo.toml`; verifies shared schema. | `runs/oct3_config_edit.toml` |
| ✅ Verified (manual) | `python -m hashmap_cli ab-compare --csv data/workloads/demo.csv --baseline-config config/config.toml --candidate-config config/config.experiment.toml --out-dir results/ab/demo` | 2025-10-04: Generates baseline/candidate artifacts + comparison JSON/Markdown. | `results/ab/demo/comparison.json` |
| ✅ Verified (manual) | `python -m hashmap_cli --config config/config.toml run-csv --csv workload.csv` | 2025-10-03: Replayed `data/workloads/w_uniform.csv` with JSON summary at `results/json/config_wizard_run.json`. | `src/adaptive_hashmap_cli.egg-info/PKG-INFO` |
| ✅ Verified (manual) | `python -m hashmap_cli generate-csv --outfile workload.csv --ops 50000 --read-ratio 0.8` | 2025-10-03: Generated sample workload after CLI modularisation. | `src/adaptive_hashmap_cli.egg-info/PKG-INFO` |
| ✅ Verified (automated) | `python -m hashmap_cli workload-dna --csv data/workloads/w_uniform.csv --top-keys 8 --pretty` | Covered by `tests/test_workload_dna.py`; outputs Workload DNA summary and optional JSON bundle. | `tests/test_workload_dna.py` |
| ✅ Verified (manual) | `python -m hashmap_cli --mode adaptive put foo bar` | 2025-10-03: Sanity check after handler extraction; see CLI refactor run log. | README |
| ✅ Verified (manual) | `python -m hashmap_cli profile --csv data/workloads/w_uniform.csv` | 2025-10-03: CLI dispatcher refactor validated; recommends fast-lookup. | README |
| ✅ Verified (manual) | `python -m hashmap_cli profile --csv data/workloads/w_uniform.csv --then get A` | 2025-10-03: Profile + follow-up command chaining still works. | README |
| ✅ Verified (manual) | `python -m hashmap_cli --json run-csv --csv data/workloads/w_uniform.csv --dry-run` | 2025-10-03: JSON dry-run emits success payload post-handler refactor. | README |
| ✅ Verified (manual) | `python -m hashmap_cli run-csv --csv data/workloads/w_uniform.csv --dry-run` | 2025-10-03: Non-JSON dry-run exercised post-handler refactor. | README |
| ✅ Verified (automated) | `python scripts/validate_metrics_ndjson.py runs/metrics.ndjson` | 2025-10-03 via `make smoke`; output archived under `runs/metrics.ndjson`. | README |
| ✅ Verified (manual) | `python -m hashmap_cli mission-control` | 2025-10-04: Config tab edits + Run Command auto-`--config` wiring; earlier heatmap legend + tooltips verified on macOS. Headless CI still uses offscreen auto-quit path. | README |
| 🟡 Pending | Mission Control → Benchmark Suites → Analyze workload (auto-launch Workload DNA tab) | Validate pyqtgraph visuals and baseline comparison in the new Workload DNA tab. | README |
| ✅ Verified (automated) | `pytest tests/test_config_wizard.py tests/test_mission_control_widgets_qt.py` | 2025-10-04: Validates CLI editor + Mission Control config pane (uses `QT_QPA_PLATFORM=offscreen`). | Test run |

## Run CSV – Phase 1 Scenarios (README)

| Status | Command | Description |
|--------|---------|-------------|
| ✅ Verified (manual) | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` | 2025-10-03: Summary regenerated post-refactor; see `results/json/perf_uniform.json`. |
| ✅ Verified (manual) | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --snapshot-out runs/phase2/adaptive_snapshot.pkl.gz --compress --json-summary-out results/json/phase2_uniform_snapshot.json --latency-sample-k 500 --latency-sample-every 64` | 2025-10-03: Snapshot-out path validated; artifacts under `runs/phase2/`. |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32` | Proactive compaction tick. |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json` | Resume from adaptive snapshot. |
| 🟡 Pending | `python -m hashmap_cli --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress` → `python -m hashmap_cli compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress` → `python -m hashmap_cli verify-snapshot --in snapshots/rh_after.pkl.gz --verbose` | Compaction + verify re-run 2025-10-03 (`runs/phase2/rh_after_phase2.pkl.gz`), but the generating `run-csv` step still pending. |
| ✅ Verified (manual) | `python -m hashmap_cli verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out runs/phase2/rh_repair_phase2.pkl.gz --verbose` | 2025-10-03: Repair path revalidated; outputs stored under `runs/phase2/`. |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16` | Adversarial stress with live metrics. |
| 🟡 Pending | `python -m hashmap_cli --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress` → `python -m hashmap_cli verify-snapshot --in snapshots/chain.pkl.gz --verbose` | Failure-path coverage. |

## Run CSV – Phase 2 / Data Inventory references

The `docs/data_inventory.md` table enumerates many dataset-specific replays. Representative commands below should be run with the corresponding CSV/snapshot assets:

| Status | Command |
|--------|---------|
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress` |
| 🟡 Pending | Tuned stress: `ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/stress_big.csv --metrics-port 8000 --json-summary-out results/json/run_stress_big_tuned.json` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/hot.csv --metrics-port 8000 --json-summary-out results/json/run_hot.json` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_low_threshold.pkl.gz --json-summary-out results/json/run_hot_lowthresh.json` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_tiny.pkl.gz --json-summary-out results/json/run_hot_tiny.json` |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/stress.csv --metrics-port 8000 --json-summary-out results/json/run_stress.json` |

## Serve Mode & Dashboard

| Status | Command | Notes |
|--------|---------|-------|
| ✅ Verified (manual) | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090` | 2025-10-03: Confirmed post-refactor (`--metrics-out-dir runs/phase1`); metrics dumps archived under `runs/phase1/`. |
| ✅ Verified (manual) | `ADHASH_TOKEN=secret python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090` | 2025-10-03: Authenticated run regenerated summary `results/json/perf_uniform_auth.json`; server trace shows gzip+auth headers. |
| ✅ Verified (manual) | `python -m hashmap_cli serve --port 9090 --source runs/metrics.ndjson --follow` | Health endpoints, gzip headers confirmed. |
| ✅ Verified (manual) | `python -m hashmap_cli serve --port 9090` + browser dashboard | 2025-10-03: Polling interval selector + throughput timeline markers verified locally (requires live workload events). |
| ✅ Verified (manual) | `ADHASH_TOKEN=secret python -m hashmap_cli serve --host 127.0.0.1 --port 9090` | 2025-10-03: Auth headers confirmed; see `runs/phase1/healthz_auth.json` + related gzip traces. |
| ✅ Verified (manual) | `python -m hashmap_cli serve --source results/ab/demo/artifacts/baseline/metrics/metrics.ndjson --compare results/ab/demo/comparison.json` | 2025-10-04: Comparison summary (ops/latency deltas) renders; `/api/compare` returns `adhash.compare.v1`. |
| ✅ Verified (manual) | `curl --compressed http://127.0.0.1:9090/api/metrics/history.csv?limit=16 -o runs/timeline.csv` | 2025-10-04: Timeline CSV export returns headers (`t,ops,…`); file saved under `runs/timeline.csv`. |
| ✅ Verified (manual) | `curl --compressed http://127.0.0.1:9090/healthz` | 2025-10-03: Captured 401 w/out token (`runs/phase1/healthz_unauth.*`) and 200 with auth (`runs/phase1/healthz_auth.*`). |
| ✅ Verified (manual) | `curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics` | 2025-10-03: Response stored at `runs/phase1/metrics_auth.*` (gzip summary schema). |
| 🟡 Pending | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` while dashboard connected | Redundant with Phase 1 row; ensure combined dashboard + summary still works. |

## Mission Control & TUI

| Status | Command | Notes |
|--------|---------|-------|
| ✅ Verified (manual) | `ADHASH_TOKEN=secret python -m hashmap_cli mission-control` | Neon theme + gzip fixes validated; ensure matching metrics port/token. |
| ✅ Verified (scripted) | `python -m hashmap_cli mission-control` (no auth) | 2025-10-03: Offscreen launch via `run_mission_control` with 500 ms `QTimer` auto-quit (PyQt6 6.9.1). |
| 🟡 Pending | `python -m hashmap_cli mission-control` (Benchmark Suites tab) | Add headless smoke to ensure the new suite manager loads specs and tails `python -m adhash.batch` output. |
| ✅ Verified (scripted) | `pip install -e '.[ui]'` → `python -m adhash.tui --metrics-endpoint http://127.0.0.1:9090/api/metrics` | 2025-10-03: Textual 6.2.1 present; auto-quit after 0.5 s using `run_async` + `action_quit`. |

## Batch Runner

| Status | Command | Notes |
|--------|---------|-------|
| ✅ Verified | `python -m adhash.batch --spec docs/examples/batch_baseline.toml` | Ensure Markdown/JSON artifacts still produce under modular layout. |
| ✅ Verified | `python -m adhash.batch --spec docs/examples/batch_compaction.toml` | Compaction-focused spec (added under docs/examples/). |
| ✅ Verified | `python -m adhash.batch --list` | Enumerate bundled specs (new CLI flag). |

## Prometheus / Dashboard Smoke

Example checks to keep handy (already exercised while validating gzip/auth):

```bash
# Headers show gzip + no-store
curl -I --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics

# Probe hist, latency hist, heatmap JSON
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/histogram/latency | jq '.schema, .operations.overall'
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/histogram/probe | jq '.schema, .buckets'
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/heatmap | jq '.schema, .rows, .cols'
```

## Automated Test Hooks

| Status | Command | Notes |
|--------|---------|-------|
| ✅ Verified (automated) | `ruff check` | Latest run passed after gzip fix. |
| ✅ Verified (automated) | `mypy src` | Latest run passed. |
| ✅ Verified (automated) | `pytest -q` | 33 passed, 1 skipped (as of latest gzip patch). |
| ✅ Verified | `make lint`, `make type`, `make test`, `make smoke` | Convenience wrappers; latest run completed successfully. |

## Follow-ups During Modularisation

- Re-run this checklist (or update statuses) after each major extraction (metrics server, snapshots, CLI commands).
- Ensure docs referencing inline dashboard assets are updated once static files move under `src/adhash/dashboard/static/`.
- Consider adding automated smoke tests for `mission-control` (headless) and the TUI when modularisation stabilises.
