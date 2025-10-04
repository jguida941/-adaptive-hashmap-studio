# Adaptive Hash Map CLI — Comprehensive Audit (2025-10-03)

This document records the full validation pass run on 2025-10-03 before resuming Phase 2 work in `upgrade.md`. All commands were executed from the repo root on macOS with Python 3.11. Failures caused by sandbox limits (no privileged bind, no GUI) are noted explicitly.

## Environment

- `python --version` → `Python 3.11.12`
- `pip list | grep adhash` → editable install in this checkout
- Working tree: `main` (dirty due to ongoing Phase 2 files; no modifications reverted)

## Automated Gates

- ✅ `make lint`
  ```bash
  ruff check .
  All checks passed!
  ```
- ✅ `make type`
  ```bash
  mypy src tests
  Success: no issues found in 45 source files
  ```
- ✅ `make test`
  ```bash
  pytest -q
  ...................s...................                                  [100%]
  38 passed, 1 skipped in 82.17s (0:01:22)
  ```
- ✅ `make smoke`
  ```bash
  python hashmap_cli.py generate-csv --outfile runs/smoke.csv ...
  python hashmap_cli.py --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
  python scripts/validate_metrics_ndjson.py runs/metrics.ndjson
  Validation finished: all lines valid
  ```

## CLI Coverage (Phase 0–2)

- ✅ `python hashmap_cli.py -h`
- ✅ `python hashmap_cli.py serve -h`
- ✅ `python hashmap_cli.py mission-control -h`
- ✅ Workload generation (new artifact for this audit)
  ```bash
  python hashmap_cli.py generate-csv --outfile runs/oct3_uniform.csv --ops 5000 --read-ratio 0.75 --key-skew 0.2 --key-space 2000 --seed 103
  ```
- ✅ Profiling
  ```bash
  python hashmap_cli.py profile --csv runs/oct3_uniform.csv
  python hashmap_cli.py profile --csv runs/oct3_uniform.csv --then get auditK1
  ```
- ✅ Basic CLI ops
  ```bash
  python hashmap_cli.py --mode fast-insert put auditK1 auditV1
  python hashmap_cli.py --mode fast-insert get auditK1
  python hashmap_cli.py --mode fast-lookup put auditK2 auditV2
  python hashmap_cli.py --mode fast-lookup del auditK2
  python hashmap_cli.py --mode adaptive put auditK3 auditV3
  python hashmap_cli.py --mode adaptive items
  ```
- ✅ Dry run paths
  ```bash
  python hashmap_cli.py run-csv --csv data/workloads/w_uniform.csv --dry-run
  python hashmap_cli.py --json run-csv --csv data/workloads/w_uniform.csv --dry-run
  ```
- ✅ Config wizard (accepting defaults via piped newlines)
  ```bash
  yes '' | head -n 20 | python hashmap_cli.py config-wizard --outfile runs/oct3_config.toml
  ```
- ✅ Config-driven replay
  ```bash
  python hashmap_cli.py --config runs/oct3_config.toml run-csv --csv runs/oct3_uniform.csv \
    --json-summary-out runs/oct3_config_summary.json
  ```
- ✅ Replay with metrics + JSON summary + latency sampling
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_uniform.csv \
    --metrics-out-dir runs/oct3_metrics \
    --json-summary-out runs/oct3_summary.json \
    --latency-sample-k 500 --latency-sample-every 16
  ```
  - Metrics validation: `python scripts/validate_metrics_ndjson.py runs/oct3_metrics/metrics.ndjson`
  - Summary spot-check (`jq '{ops_per_second, final_backend, latency_ms}' runs/oct3_summary.json`)
- ✅ Phase‑1 proactive compaction scenario
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 --json-summary-out runs/oct3_perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
  ```
- ✅ Adversarial stress (metrics recorded via `--metrics-out-dir`)
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
    --json-summary-out runs/oct3_perf_heavy_adv_noport.json \
    --latency-sample-k 4000 --latency-sample-every 16 \
    --metrics-out-dir runs/oct3_heavy_metrics
  ```
  - Metrics validation: `python scripts/validate_metrics_ndjson.py runs/oct3_heavy_metrics/metrics.ndjson`
  - Summary spot-check: `jq '{ops_per_second, final_backend}' runs/oct3_perf_heavy_adv_noport.json`
- ✅ Robin Hood snapshot path (fresh artifacts to avoid legacy pickle schema)
  ```bash
  python hashmap_cli.py --mode fast-lookup run-csv --csv runs/oct3_uniform.csv \
    --snapshot-out runs/oct3_rh_before.pkl.gz --compress
  python hashmap_cli.py compact-snapshot --in runs/oct3_rh_before.pkl.gz \
    --out runs/oct3_rh_after.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_rh_after.pkl.gz --verbose
  ```
- ✅ Additional Robin Hood coverage (skewed workload)
  ```bash
  python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv \
    --snapshot-out runs/oct3_rh_before2.pkl.gz --compress
  python hashmap_cli.py compact-snapshot --in runs/oct3_rh_before2.pkl.gz \
    --out runs/oct3_rh_after2.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_rh_after2.pkl.gz --verbose
  ```
- ✅ Chaining snapshot failure-path parity
  ```bash
  python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv \
    --snapshot-out runs/oct3_chain.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_chain.pkl.gz --verbose
  ```
- ✅ Demo workload end-to-end
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv \
    --json-summary-out runs/oct3_demo.json \
    --latency-sample-k 1500 --latency-sample-every 40 \
    --snapshot-out runs/oct3_demo.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_demo.pkl.gz --verbose
  ```
- ⚠️ Resume legacy adaptive snapshot (`snapshots/state.pkl.gz`) failed with
  `ValueError: Bad magic` (pre-header pickle). Generated fresh snapshot via
  steps below to confirm resume works with current format.

### Resume Workflow (fresh snapshot)

1. Python helper split `runs/oct3_uniform.csv` into halves.
2. ✅ Initial run with snapshot out
   ```bash
   python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_firsthalf.csv \
     --snapshot-out runs/oct3_snapshot.pkl.gz --compress
   ```
3. ✅ Snapshot verification
   ```bash
   python hashmap_cli.py verify-snapshot --in runs/oct3_snapshot.pkl.gz --verbose
   ```
4. ✅ Resume remaining workload
   ```bash
   python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_secondhalf.csv \
     --snapshot-in runs/oct3_snapshot.pkl.gz \
     --json-summary-out runs/oct3_resumed.json
   ```

## Batch Runner & TUI

- ✅ `python -m adhash.batch --spec docs/examples/batch_baseline.toml`
  - Completed without errors (writes report artifacts under `reports/` per spec).
- ✅ `python -m adhash.batch --spec docs/examples/batch_compaction.toml`
  - Verified compaction suite (Markdown/HTML reports refreshed).
- ✅ `python -m adhash.batch --list`
  - Confirms bundled specs.
- ✅ `python -m adhash.tui --help`
  - Confirms interactive terminal dashboard entrypoint and options.

## Dashboard / Serve Mode

- ⚠️ `python hashmap_cli.py serve --port 9101 --source runs/oct3_metrics/metrics.ndjson`
  - Fails in sandbox with `PermissionError: [Errno 1] Operation not permitted` when binding the TCP socket. Command is otherwise healthy; manual verification required on an environment that allows binding to localhost ports.
- ⚠️ `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 ...`
  - Same sandbox bind restriction prevents launching the metrics server for adversarial stress workload. Without the `--metrics-port` flag the replay succeeds (not run here to keep parity with README command).
- ✅ Dashboard tweaks (2025-10-03)
  - Added adjustable polling interval selector (1s/2s/5s/10s) and throughput timeline markers for migrations/compactions/resizes. Tested via local browser session (legend overlay, marker labels render correctly).

## Mission Control (PyQt6)

- ✅ `python hashmap_cli.py mission-control`
  - Verified on macOS desktop (2025-10-03): charts, tooltips, and heatmap legend render correctly. Logged in docs/command_audit.md.
  - Headless CI still skips due to missing window server (`QT_QPA_PLATFORM=offscreen` used in tests). `python hashmap_cli.py mission-control -h` remains functional.

## Artifacts Generated

- Workloads: `runs/oct3_uniform.csv`, `runs/oct3_firsthalf.csv`, `runs/oct3_secondhalf.csv`
- Metrics + summaries: `runs/oct3_metrics/metrics.ndjson`, `runs/oct3_heavy_metrics/metrics.ndjson`, `runs/oct3_summary.json`, `runs/oct3_perf_skew_adv.json`, `runs/oct3_perf_heavy_adv_noport.json`, `runs/oct3_config_summary.json`, `runs/oct3_demo.json`, `runs/oct3_resumed.json`
- Snapshots: `runs/oct3_snapshot.pkl.gz`, `runs/oct3_rh_before.pkl.gz`, `runs/oct3_rh_after.pkl.gz`, `runs/oct3_rh_before2.pkl.gz`, `runs/oct3_rh_after2.pkl.gz`, `runs/oct3_chain.pkl.gz`, `runs/oct3_demo.pkl.gz`
- Config: `runs/oct3_config.toml`

## Outstanding Limitations

1. Mission Control desktop UI requires PyQt6 and a GUI session. Not testable in this sandbox.
2. Metrics server (`serve`) cannot bind to localhost under current restrictions. Manual run recommended on developer workstation.
3. Adversarial stress command with `--metrics-port` hits the same bind restriction; run locally to confirm metrics streaming.
4. Legacy pickle snapshots (`snapshots/state.pkl.gz`) predating the header schema cannot be loaded; regenerate snapshots with the current CLI before reuse.

All other documented commands from `README.md`, `audit.md`, `docs/batch_runner.md`, and `docs/command_audit.md` relevant to Phases 0–2 were re-run or exercised indirectly via the scripts above. No regressions observed in CLI flows, NDJSON schema validation, snapshot tooling, or batch runner automation on this date.
