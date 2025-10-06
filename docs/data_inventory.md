# Data Inventory

This repository bundles artifacts from the September 22, 2025 baseline audit and the October 1–2, 2025 Phase 2 checkpoint. Use this document as a map from files to the commands that produced them and the docs where each artifact is discussed.

```
repo/
├── audit.md
├── oct1_audit.md
├── data/
│   ├── config/
│   │   └── example_migration.cfg
│   └── workloads/
│       ├── demo.csv
│       ├── hot.csv
│       ├── oct1_demo.csv
│       ├── oct1_w_heavy_adv.csv
│       ├── oct1_w_skew_adv.csv
│       ├── oct1_w_uniform.csv
│       ├── oct1_w_uniform_half.csv
│       ├── oct1_w_uniform_rest.csv
│       ├── stress.csv
│       ├── stress_big.csv
│       ├── stress_huge.csv
│       ├── w_heavy_adv.csv
│       ├── w_skew_adv.csv
│       ├── w_uniform.csv
│       ├── w_uniform_half.csv
│       └── w_uniform_rest.csv
├── results/
│   └── json/
│       ├── demo_perf.json
│       ├── oct1_demo_perf.json
│       ├── oct1_perf_heavy_adv.json
│       ├── oct1_perf_rest.json
│       ├── oct1_perf_skew_adv.json
│       ├── oct1_perf_uniform.json
│       ├── perf_heavy_adv.json
│       ├── perf_rest.json
│       ├── perf_skew_adv.json
│       ├── perf_uniform.json
│       ├── run_hot.json
│       ├── run_hot_lowthresh.json
│       ├── run_hot_tiny.json
│       ├── run_stress.json
│       └── run_stress_big_tuned.json
├── snapshots/
│   ├── adaptive_low_threshold.pkl.gz
│   ├── adaptive_tiny.pkl.gz
│   ├── chain.pkl.gz
│   ├── demo.pkl.gz
│   ├── oct1_chain.pkl.gz
│   ├── oct1_demo.pkl.gz
│   ├── oct1_rh_after.pkl.gz
│   ├── oct1_rh_before.pkl.gz
│   ├── oct1_rh_fixed.pkl.gz
│   ├── oct1_state.pkl.gz
│   ├── rh_after.pkl.gz
│   ├── rh_before.pkl.gz
│   ├── rh_fixed.pkl.gz
│   └── state.pkl.gz
├── scripts/validate_metrics_ndjson.py
├── tests/test_perf_smoke.py
└── docs/
    ├── grafana_dashboard.json
    └── prometheus_grafana.md
```

Artifacts prefixed with `oct1_` were produced during the October 2025 audit pass documented in [`oct1_audit.md`](../oct1_audit.md); the tables below list the exact commands.

## Workloads (`data/workloads/`)

| File | Command | Purpose |
|------|---------|---------|
| `data/workloads/w_uniform.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42` | Baseline uniform workload (Sections 1 & 3 of the audit). |
| `data/workloads/w_uniform_half.csv` | Part of the split helper in audit Step 6 (Python snippet writes half + rest) | First 50k operations used to create `snapshots/state.pkl.gz`. |
| `data/workloads/w_uniform_rest.csv` | Same helper as above | Remaining 50k operations replayed after loading `state.pkl.gz`. |
| `data/workloads/w_skew_adv.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8` | Zipf + adversarial workload for profiling, compaction and snapshot repair (Sections 1, 5, 7, 8). |
| `data/workloads/w_heavy_adv.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10` | High-pressure adversarial stress replayed with live metrics (Section 10). |
| `data/workloads/demo.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7` | End-to-end “demo” flow (Section 13). |
| `data/workloads/hot.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/hot.csv --ops 200000 --read-ratio 0.10 --key-skew 1.2 --key-space 5000 --adversarial-ratio 0.90 --adversarial-lowbits 8 --seed 42` | High-collision workload used while experimenting with migration thresholds. |
| `data/workloads/stress.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/stress.csv --ops 200000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 42` | Baseline adversarial workload for the “force migration” demo. |
| `data/workloads/stress_big.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/stress_big.csv --ops 600000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 4242` | Larger variant used with environment overrides to show repeated migrations. |
| `data/workloads/stress_huge.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/stress_huge.csv --ops 2000000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 777` | Reserved future workload for extended profiling (not yet replayed). |
| `data/workloads/oct1_w_uniform.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/oct1_w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42` | Phase 2 re-run of the uniform workload (Oct 1 audit Step 1). |
| `data/workloads/oct1_w_uniform_half.csv` | Split helper (`python -c '...'`) mirroring Step 6, targeting the Oct 1 CSV | First 50k operations for `snapshots/oct1_state.pkl.gz`. |
| `data/workloads/oct1_w_uniform_rest.csv` | Same helper as above | Remaining 50k operations replayed after loading `oct1_state.pkl.gz`. |
| `data/workloads/oct1_w_skew_adv.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/oct1_w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8` | Oct 1 skew/adversarial workload (profiling + compaction + snapshot repair). |
| `data/workloads/oct1_w_heavy_adv.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/oct1_w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10` | Oct 1 adversarial stress replayed with live metrics (Step 10). |
| `data/workloads/oct1_demo.csv` | `python -m hashmap_cli generate-csv --outfile data/workloads/oct1_demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7` | Oct 1 end-to-end demo workload. |

## Config (`data/config/`)

| File | Purpose |
|------|---------|
| `example_migration.cfg` | Sample threshold overrides documented in the README. Imported manually when experimenting with forced migrations. |

## Snapshots (`snapshots/`)

| File | Created By | Notes |
|------|------------|-------|
| `snapshots/state.pkl.gz` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv --snapshot-out snapshots/state.pkl.gz --compress` | Adaptive snapshot saved midway through the uniform workload (Step 6). |
| `snapshots/rh_before.pkl.gz` | `python -m hashmap_cli --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress` | RobinHood-only snapshot before offline compaction (Step 7). |
| `snapshots/rh_after.pkl.gz` | `python -m hashmap_cli compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress` | Compacted RobinHood snapshot (Step 7). |
| `snapshots/rh_fixed.pkl.gz` | `python -m hashmap_cli verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose` | Output of the safe repair path (Step 8). |
| `snapshots/chain.pkl.gz` | `python -m hashmap_cli --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress` | TwoLevelChaining snapshot used to show that `compact-snapshot` rejects non-RobinHood inputs (Step 12). |
| `snapshots/demo.pkl.gz` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress` | Snapshot produced by the optional end-to-end demo (Section 13). |
| `snapshots/oct1_state.pkl.gz` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_half.csv --snapshot-out snapshots/oct1_state.pkl.gz --compress` | Oct 1 adaptive snapshot saved midway through the uniform workload (Step 6, Oct 1 audit). |
| `snapshots/oct1_rh_before.pkl.gz` | `python -m hashmap_cli --mode fast-lookup run-csv --csv data/workloads/oct1_w_skew_adv.csv --snapshot-out snapshots/oct1_rh_before.pkl.gz --compress` | Oct 1 RobinHood snapshot captured before offline compaction (Step 7). |
| `snapshots/oct1_rh_after.pkl.gz` | `python -m hashmap_cli compact-snapshot --in snapshots/oct1_rh_before.pkl.gz --out snapshots/oct1_rh_after.pkl.gz --compress` | Oct 1 compacted RobinHood snapshot (Step 7). |
| `snapshots/oct1_rh_fixed.pkl.gz` | `python -m hashmap_cli verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --repair --out snapshots/oct1_rh_fixed.pkl.gz --verbose` | Oct 1 safe repair output (Step 8). |
| `snapshots/oct1_chain.pkl.gz` | `python -m hashmap_cli --mode fast-insert run-csv --csv data/workloads/oct1_w_uniform.csv --snapshot-out snapshots/oct1_chain.pkl.gz --compress` | Oct 1 chaining snapshot used to confirm `compact-snapshot` fails as expected (Step 12). |
| `snapshots/oct1_demo.pkl.gz` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress` | Oct 1 demo snapshot. |
| `snapshots/adaptive_low_threshold.pkl.gz` | Inline `python - <<'PY'` helper (HybridAdaptiveHashMap with `max_group_len=2`, `max_lf_chaining=0.55`) | Minimal snapshot used internally to test migration callbacks (kept for reproducibility). |
| `snapshots/adaptive_tiny.pkl.gz` | Inline helper creating `HybridAdaptiveHashMap(initial_buckets=8, groups_per_bucket=1)` | Tiny adaptive snapshot that migrates immediately; referenced in migration experiments. |

## JSON Summaries (`results/json/`)

| File | Command | Highlights |
|------|---------|------------|
| `results/json/perf_uniform.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` | Baseline: ~2.28k ops/s, chaining backend, per-op latency percentiles recorded. |
| `results/json/perf_skew_adv.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32` | Zipf + adversarial workload with proactive compaction. |
| `results/json/perf_rest.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json` | Resume run from `snapshots/state.pkl.gz`. |
| `results/json/perf_heavy_adv.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16` | Heavy adversarial replay (Section 10). |
| `results/json/demo_perf.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress` | Metrics for the full demo pipeline. |
| `results/json/run_hot.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/hot.csv --metrics-port 8000 --json-summary-out results/json/run_hot.json` | High-collision workload before tightening thresholds (stays on chaining). |
| `results/json/run_hot_lowthresh.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_low_threshold.pkl.gz --json-summary-out results/json/run_hot_lowthresh.json` | Demonstrates custom thresholds with a preconfigured adaptive snapshot. |
| `results/json/run_hot_tiny.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_tiny.pkl.gz --json-summary-out results/json/run_hot_tiny.json` | Verifies that the tiny adaptive snapshot migrates immediately. |
| `results/json/run_stress.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/stress.csv --metrics-port 8000 --json-summary-out results/json/run_stress.json` | Default thresholds; lightly stressed workload remaining on chaining. |
| `results/json/run_stress_big_tuned.json` | `ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/stress_big.csv --metrics-port 8000 --json-summary-out results/json/run_stress_big_tuned.json` | Tuned thresholds: repeated migrations, backend finishes on Robin Hood (~43k ops/s). |
| `results/json/oct1_perf_uniform.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` | Oct 1 baseline summary (Phase 2 verification). |
| `results/json/oct1_perf_skew_adv.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32` | Oct 1 proactive compaction tick. |
| `results/json/oct1_perf_rest.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json` | Oct 1 resume from adaptive snapshot. |
| `results/json/oct1_perf_heavy_adv.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16` | Oct 1 adversarial stress replay. |
| `results/json/oct1_demo_perf.json` | `python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress` | Oct 1 end-to-end demo metrics. |

## Supporting Docs

- `audit.md` – baseline checklist with linked commands (Phase 0–2 crosswalk now included).
- `oct1_audit.md` – detailed log of the October 1, 2025 rerun (mirrors Phase 2 scope with `oct1_*` artifacts).
- `README.md` – project overview, quick start, and the new Phase 0–2 command index.
- `upgrade.md` – phased roadmap and status (Phase 2 currently in progress).
- `docs/prometheus_grafana.md` – Prometheus scrape configuration, example alert rules, and Grafana setup walk-through.
- `docs/grafana_dashboard.json` – Importable Grafana dashboard highlighting load factor, probe distance, throughput, and alert context.
- `docs/config.md` – TOML configuration schema and override precedence.
- `docs/batch_runner.md` – Batch runner spec reference and usage guide.
- `docs/serve_mode.md` – Sticky dashboard/metrics serve mode instructions.
- `tests/test_perf_smoke.py` – CI-friendly throughput regression confirming `metrics.v1` emission.
- `tests/test_metrics_endpoints.py` – Contract tests for histogram/heatmap REST endpoints.
- `tests/test_latency_buckets.py` – Covers the latency histogram bucket presets (default vs. micro).
- `tests/test_process_manager.py` – Ensures the Mission Control subprocess manager captures output and stops cleanly.
- `tests/test_mission_control_stub.py` – Ensures the Mission Control launcher reports missing PyQt6 clearly.
- `src/adhash/tui/` – Textual-based terminal dashboard (`python -m adhash.tui`) with live summaries/alerts (Phase 2).
- `src/adhash/mission_control/` – PyQt6 Mission Control scaffolding (`python -m adhash.mission_control`).
- `docs/examples/batch_baseline.toml` – Sample batch-runner spec used in README and audit.
