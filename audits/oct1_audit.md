# Audit for October 1, 2025

This file documents the execution and verification of all commands for the AdaptiveHashMapCli project.

## 0) Sanity: help + modes
- [x] `python hashmap_cli.py -h`
- [x] `python hashmap_cli.py --mode fast-insert put A 1`
- [x] `python hashmap_cli.py --mode fast-lookup get A`
- [x] `python hashmap_cli.py --mode adaptive items`

*Note: `get` and `items` commands return no output as the CLI is stateless and each command is a separate execution.*

## 1) Generate workloads (uniform + skewed + adversarial)
- [x] `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`
- [x] `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8`

## 2) Quick profile (backend recommendation)
- [x] `python hashmap_cli.py profile --csv data/workloads/oct1_w_uniform.csv`
- [x] `python hashmap_cli.py profile --csv data/workloads/oct1_w_uniform.csv --then get A`

## 3) Run a workload with live metrics + dashboard
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --metrics-port 9091`

## 4) Run with JSON summary + latency percentiles (reservoir sampling)
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`

## 5) Proactive compaction tick (time-based)
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`

## 6) Snapshot save + load + continue
- [x] `python -c 'from pathlib import Path; src = Path("data/workloads/oct1_w_uniform.csv").read_text().splitlines(); header, rows = src[0], src[1:]; midpoint = 50_000; Path("data/workloads/oct1_w_uniform_half.csv").write_text("\n".join([header] + rows[:midpoint]) + "\n"); Path("data/workloads/oct1_w_uniform_rest.csv").write_text("\n".join([header] + rows[midpoint:]) + "\n")'`
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_half.csv --snapshot-out snapshots/oct1_state.pkl.gz --compress`
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_state.pkl.gz --verbose`
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json`

## 7) Offline compaction for a RobinHood snapshot
- [x] `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/oct1_w_skew_adv.csv --snapshot-out snapshots/oct1_rh_before.pkl.gz --compress`
- [x] `python hashmap_cli.py compact-snapshot --in snapshots/oct1_rh_before.pkl.gz --out snapshots/oct1_rh_after.pkl.gz --compress`
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --verbose`
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_after.pkl.gz --verbose`

## 8) Verify + safe repair (RobinHood compaction) with output
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --repair --out snapshots/oct1_rh_fixed.pkl.gz --verbose`

## 9) One-shot CLI ops smoke test (explicit modes)
- [x] `python hashmap_cli.py --mode fast-insert put K1 V1`
- [x] `python hashmap_cli.py --mode fast-insert get K1`
- [x] `python hashmap_cli.py --mode fast-lookup put K2 V2`
- [x] `python hashmap_cli.py --mode fast-lookup del K2`
- [x] `python hashmap_cli.py --mode adaptive put K3 V3`
- [x] `python hashmap_cli.py --mode adaptive items`

*Note: The one-shot commands in this section execute successfully, but do not share state. For example, `get K1` does not return a value because the `put K1 V1` command was a separate process.*

## 10) Adversarial stress + metrics (watch migrations)
- [x] `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10`
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`

## 11) Minimal smoke with items (visual check)
- [x] `python hashmap_cli.py --mode adaptive put foo bar`
- [x] `python hashmap_cli.py --mode adaptive put baz qux`
- [x] `python hashmap_cli.py --mode adaptive items`

## 12) Failure-path check: verify wrong type
- [x] `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/oct1_w_uniform.csv --snapshot-out snapshots/oct1_chain.pkl.gz --compress`
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_chain.pkl.gz --verbose`
- [x] `python hashmap_cli.py compact-snapshot --in snapshots/oct1_chain.pkl.gz --out snapshots/oct1_chain_compacted.pkl.gz --compress` (failed as expected)

## 13) One-shot demo (optional end-to-end)
- [x] `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`
- [x] `python hashmap_cli.py profile --csv data/workloads/oct1_demo.csv`
- [x] `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress`
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_demo.pkl.gz --verbose`
- [x] `python hashmap_cli.py compact-snapshot --in snapshots/oct1_demo.pkl.gz --out snapshots/oct1_demo_compacted.pkl.gz --compress || true` (failed as expected)
- [x] `python hashmap_cli.py verify-snapshot --in snapshots/oct1_demo.pkl.gz --repair --out snapshots/oct1_demo_fixed.pkl.gz --verbose`
