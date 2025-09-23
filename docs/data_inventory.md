# Data Inventory

This repository bundles every artifact produced during the September 22, 2025 audit so future runs are repeatable and traceable. Use this document as a map from files to the commands that created them.

```
repo/
├── data/
│   ├── config/
│   │   └── example_migration.cfg
│   └── workloads/
│       ├── demo.csv
│       ├── hot.csv
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
│   ├── rh_after.pkl.gz
│   ├── rh_before.pkl.gz
│   ├── rh_fixed.pkl.gz
│   └── state.pkl.gz
├── README.md
└── audit.md
```

## Workloads (`data/workloads/`)

| File | Command | Purpose |
|------|---------|---------|
| `data/workloads/w_uniform.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42` | Baseline uniform workload (Sections 1 & 3 of the audit). |
| `data/workloads/w_uniform_half.csv` | Part of the split helper in audit Step 6 (Python snippet writes half + rest) | First 50k operations used to create `snapshots/state.pkl.gz`. |
| `data/workloads/w_uniform_rest.csv` | Same helper as above | Remaining 50k operations replayed after loading `state.pkl.gz`. |
| `data/workloads/w_skew_adv.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8` | Zipf + adversarial workload for profiling, compaction and snapshot repair (Sections 1, 5, 7, 8). |
| `data/workloads/w_heavy_adv.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10` | High-pressure adversarial stress replayed with live metrics (Section 10). |
| `data/workloads/demo.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7` | End-to-end “demo” flow (Section 13). |
| `data/workloads/hot.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/hot.csv --ops 200000 --read-ratio 0.10 --key-skew 1.2 --key-space 5000 --adversarial-ratio 0.90 --adversarial-lowbits 8 --seed 42` | High-collision workload used while experimenting with migration thresholds. |
| `data/workloads/stress.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/stress.csv --ops 200000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 42` | Baseline adversarial workload for the “force migration” demo. |
| `data/workloads/stress_big.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/stress_big.csv --ops 600000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 4242` | Larger variant used with environment overrides to show repeated migrations. |
| `data/workloads/stress_huge.csv` | `python hashmap_cli.py generate-csv --outfile data/workloads/stress_huge.csv --ops 2000000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 777` | Reserved future workload for extended profiling (not yet replayed). |

## Config (`data/config/`)

| File | Purpose |
|------|---------|
| `example_migration.cfg` | Sample threshold overrides documented in the README. Imported manually when experimenting with forced migrations. |

## Snapshots (`snapshots/`)

| File | Created By | Notes |
|------|------------|-------|
| `snapshots/state.pkl.gz` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv --snapshot-out snapshots/state.pkl.gz --compress` | Adaptive snapshot saved midway through the uniform workload (Step 6). |
| `snapshots/rh_before.pkl.gz` | `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress` | RobinHood-only snapshot before offline compaction (Step 7). |
| `snapshots/rh_after.pkl.gz` | `python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress` | Compacted RobinHood snapshot (Step 7). |
| `snapshots/rh_fixed.pkl.gz` | `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose` | Output of the safe repair path (Step 8). |
| `snapshots/chain.pkl.gz` | `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress` | TwoLevelChaining snapshot used to show that `compact-snapshot` rejects non-RobinHood inputs (Step 12). |
| `snapshots/demo.pkl.gz` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress` | Snapshot produced by the optional end-to-end demo (Section 13). |
| `snapshots/adaptive_low_threshold.pkl.gz` | Inline `python - <<'PY'` helper (HybridAdaptiveHashMap with `max_group_len=2`, `max_lf_chaining=0.55`) | Minimal snapshot used internally to test migration callbacks (kept for reproducibility). |
| `snapshots/adaptive_tiny.pkl.gz` | Inline helper creating `HybridAdaptiveHashMap(initial_buckets=8, groups_per_bucket=1)` | Tiny adaptive snapshot that migrates immediately; referenced in migration experiments. |

## JSON Summaries (`results/json/`)

| File | Command | Highlights |
|------|---------|------------|
| `results/json/perf_uniform.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` | Baseline: ~2.28k ops/s, chaining backend, per-op latency percentiles recorded. |
| `results/json/perf_skew_adv.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32` | Zipf + adversarial workload with proactive compaction. |
| `results/json/perf_rest.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json` | Resume run from `snapshots/state.pkl.gz`. |
| `results/json/perf_heavy_adv.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16` | Heavy adversarial replay (Section 10). |
| `results/json/demo_perf.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress` | Metrics for the full demo pipeline. |
| `results/json/run_hot.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --metrics-port 8000 --json-summary-out results/json/run_hot.json` | High-collision workload before tightening thresholds (stays on chaining). |
| `results/json/run_hot_lowthresh.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_low_threshold.pkl.gz --json-summary-out results/json/run_hot_lowthresh.json` | Demonstrates custom thresholds with a preconfigured adaptive snapshot. |
| `results/json/run_hot_tiny.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_tiny.pkl.gz --json-summary-out results/json/run_hot_tiny.json` | Verifies that the tiny adaptive snapshot migrates immediately. |
| `results/json/run_stress.json` | `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress.csv --metrics-port 8000 --json-summary-out results/json/run_stress.json` | Default thresholds; lightly stressed workload remaining on chaining. |
| `results/json/run_stress_big_tuned.json` | `ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress_big.csv --metrics-port 8000 --json-summary-out results/json/run_stress_big_tuned.json` | Tuned thresholds: repeated migrations, backend finishes on Robin Hood (~43k ops/s). |

## Supporting Docs

- `audit.md` – full checklist with boxes ticked after executing every command.
- `README.md` – project overview, quick start, and migration demo instructions.
