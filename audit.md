# Adaptive HashMap CLI Audit Checklist

> Use this list to run and confirm every keyed path. Mark each item when the command succeeds without errors and behaves as expected.
> All paths assume you are in the repo root where workloads live in `data/workloads/`, snapshots in `snapshots/`, and JSON summaries in `results/json/`.

## 0) Sanity: help + modes
- [x] `python hashmap_cli.py -h`
- [x] `python hashmap_cli.py --mode fast-insert put A 1`
- [x] `python hashmap_cli.py --mode fast-lookup get A`
- [x] `python hashmap_cli.py --mode adaptive items`

## 1) Generate workloads (uniform + skewed + adversarial)
- [x]
  ```bash
  python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42
  ```
- [x]
  ```bash
  python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 \
    --adversarial-ratio 0.10 --adversarial-lowbits 8
  ```

## 2) Quick profile (backend recommendation)
- [x] `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv`
- [x] `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A`

## 3) Run a workload with live metrics + dashboard
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090
  ```

## 4) Run with JSON summary + latency percentiles (reservoir sampling)
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv \
    --json-summary-out results/json/perf_uniform.json \
    --latency-sample-k 2000 --latency-sample-every 64
  ```
- [x] `cat results/json/perf_uniform.json`

## 5) Proactive compaction tick (time-based)
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 \
    --json-summary-out results/json/perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
  ```

## 6) Snapshot save + load + continue
- [x]
  ```bash
  python - <<'PY'
  from pathlib import Path

  src = Path("data/workloads/w_uniform.csv").read_text().splitlines()
  header, rows = src[0], src[1:]
  midpoint = 50_000

  Path("data/workloads/w_uniform_half.csv").write_text("\n".join([header] + rows[:midpoint]) + "\n")
  Path("data/workloads/w_uniform_rest.csv").write_text("\n".join([header] + rows[midpoint:]) + "\n")
  PY
  ```
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv \
    --snapshot-out snapshots/state.pkl.gz --compress
  ```
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/state.pkl.gz --verbose`
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv \
    --snapshot-in snapshots/state.pkl.gz \
    --json-summary-out results/json/perf_rest.json
  ```

## 7) Offline compaction for a RobinHood snapshot
- [x]
  ```bash
  python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress
  ```
- [x]
  ```bash
  python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress
  ```
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --verbose`
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/rh_after.pkl.gz --verbose`

## 8) Verify + safe repair (RobinHood compaction) with output
- [x]
  ```bash
  python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose
  ```

## 9) One-shot CLI ops smoke test (explicit modes)
- [x] `python hashmap_cli.py --mode fast-insert put K1 V1`
- [x] `python hashmap_cli.py --mode fast-insert get K1`
- [x] `python hashmap_cli.py --mode fast-lookup put K2 V2`
- [x] `python hashmap_cli.py --mode fast-lookup del K2`
- [x] `python hashmap_cli.py --mode adaptive put K3 V3`
- [x] `python hashmap_cli.py --mode adaptive items`

## 10) Adversarial stress + metrics (watch migrations)
- [x]
  ```bash
  python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 \
    --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10
  ```
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
    --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16
  ```

## 11) Minimal smoke with items (visual check)
- [x] `python hashmap_cli.py --mode adaptive put foo bar`
- [x] `python hashmap_cli.py --mode adaptive put baz qux`
- [x] `python hashmap_cli.py --mode adaptive items`

## 12) Failure-path check: verify wrong type
- [x]
  ```bash
  python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress
  ```
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/chain.pkl.gz --verbose`
- [ ] `# intentionally skip: compact-snapshot on chaining snapshot (should fail)`

## One-shot demo (optional end-to-end)
- [x]
  ```bash
  python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7
  ```
- [x] `python hashmap_cli.py profile --csv data/workloads/demo.csv`
- [x]
  ```bash
  python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress
  ```
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --verbose`
- [x] `python hashmap_cli.py compact-snapshot --in snapshots/demo.pkl.gz --out snapshots/demo_compacted.pkl.gz --compress || true`
- [x]
  ```bash
  python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --repair --out snapshots/demo_fixed.pkl.gz --verbose
  ```

---

*Notes*
- Tick each box once the command succeeds and any artifacts (CSV, JSON, snapshots) look correct.
- Record anomalies or stderr under the corresponding command for follow-up.
- Step 6: The Python helper preserves headers while splitting the uniform workload.
