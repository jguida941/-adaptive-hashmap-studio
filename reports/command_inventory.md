# Command Inventory

Generated from audits/docs.

## audit.md
- `python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`

```bash
python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 \
    --adversarial-ratio 0.10 --adversarial-lowbits 8
```
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090`

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv \
    --json-summary-out results/json/perf_uniform.json \
    --latency-sample-k 2000 --latency-sample-every 64
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 \
    --json-summary-out results/json/perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
```

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

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv \
    --snapshot-out snapshots/state.pkl.gz --compress
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv \
    --snapshot-in snapshots/state.pkl.gz \
    --json-summary-out results/json/perf_rest.json
```
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress`
- `python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose`

```bash
python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 \
    --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
    --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16
```
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress`
- `python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --repair --out snapshots/demo_fixed.pkl.gz --verbose`
- `python hashmap_cli.py -h`
- `python hashmap_cli.py --mode fast-insert put A 1`
- `python hashmap_cli.py --mode fast-lookup get A`
- `python hashmap_cli.py --mode adaptive items`
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv`
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A`
- `cat results/json/perf_uniform.json`
- `python hashmap_cli.py verify-snapshot --in snapshots/state.pkl.gz --verbose`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --verbose`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_after.pkl.gz --verbose`
- `python hashmap_cli.py --mode fast-insert put K1 V1`
- `python hashmap_cli.py --mode fast-insert get K1`
- `python hashmap_cli.py --mode fast-lookup put K2 V2`
- `python hashmap_cli.py --mode fast-lookup del K2`
- `python hashmap_cli.py --mode adaptive put K3 V3`
- `python hashmap_cli.py --mode adaptive items`
- `python hashmap_cli.py --mode adaptive put foo bar`
- `python hashmap_cli.py --mode adaptive put baz qux`
- `python hashmap_cli.py --mode adaptive items`
- `python hashmap_cli.py verify-snapshot --in snapshots/chain.pkl.gz --verbose`
- `# intentionally skip: compact-snapshot on chaining snapshot (should fail)`
- `python hashmap_cli.py profile --csv data/workloads/demo.csv`
- `python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --verbose`
- `python hashmap_cli.py compact-snapshot --in snapshots/demo.pkl.gz --out snapshots/demo_compacted.pkl.gz --compress || true`
- `make lint`
- `ruff check .`
- `make type`
- `mypy .`
- `make test`
- `pytest -q`
- `make smoke`
- `python scripts/validate_metrics_ndjson.py runs/metrics.ndjson`
- `make smoke`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json`
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress`
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv`
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python -m adhash.tui --metrics-endpoint http://127.0.0.1:9090/api/metrics`
- `python hashmap_cli.py serve --port 9090 --source runs/metrics.ndjson --follow`
- `python -m adhash.batch --spec docs/examples/batch_baseline.toml`
- `python hashmap_cli.py mission-control`
- `pip install .[gui]`
- `python scripts/query_metric_endpoint.py http://127.0.0.1:9090/api/metrics/histogram/latency operations.overall`
- `python scripts/query_metric_endpoint.py http://127.0.0.1:9090/api/metrics/histogram/probe buckets`
- `curl http://127.0.0.1:9090/api/metrics/heatmap | jq '.rows, .cols, .total'`
- `ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --latency-buckets micro --metrics-port 9090`
- `python hashmap_cli.py --mode adaptive items`
- `python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`

## oct1_audit.md
- `python hashmap_cli.py -h`
- `python hashmap_cli.py --mode fast-insert put A 1`
- `python hashmap_cli.py --mode fast-lookup get A`
- `python hashmap_cli.py --mode adaptive items`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8`
- `python hashmap_cli.py profile --csv data/workloads/oct1_w_uniform.csv`
- `python hashmap_cli.py profile --csv data/workloads/oct1_w_uniform.csv --then get A`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --metrics-port 9091`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`
- `python -c 'from pathlib import Path; src = Path("data/workloads/oct1_w_uniform.csv").read_text().splitlines(); header, rows = src[0], src[1:]; midpoint = 50_000; Path("data/workloads/oct1_w_uniform_half.csv").write_text("\n".join([header] + rows[:midpoint]) + "\n"); Path("data/workloads/oct1_w_uniform_rest.csv").write_text("\n".join([header] + rows[midpoint:]) + "\n")'`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_half.csv --snapshot-out snapshots/oct1_state.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_state.pkl.gz --verbose`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json`
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/oct1_w_skew_adv.csv --snapshot-out snapshots/oct1_rh_before.pkl.gz --compress`
- `python hashmap_cli.py compact-snapshot --in snapshots/oct1_rh_before.pkl.gz --out snapshots/oct1_rh_after.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --verbose`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_after.pkl.gz --verbose`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --repair --out snapshots/oct1_rh_fixed.pkl.gz --verbose`
- `python hashmap_cli.py --mode fast-insert put K1 V1`
- `python hashmap_cli.py --mode fast-insert get K1`
- `python hashmap_cli.py --mode fast-lookup put K2 V2`
- `python hashmap_cli.py --mode fast-lookup del K2`
- `python hashmap_cli.py --mode adaptive put K3 V3`
- `python hashmap_cli.py --mode adaptive items`
- `get K1`
- `put K1 V1`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`
- `python hashmap_cli.py --mode adaptive put foo bar`
- `python hashmap_cli.py --mode adaptive put baz qux`
- `python hashmap_cli.py --mode adaptive items`
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/oct1_w_uniform.csv --snapshot-out snapshots/oct1_chain.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_chain.pkl.gz --verbose`
- `python hashmap_cli.py compact-snapshot --in snapshots/oct1_chain.pkl.gz --out snapshots/oct1_chain_compacted.pkl.gz --compress`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`
- `python hashmap_cli.py profile --csv data/workloads/oct1_demo.csv`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_demo.pkl.gz --verbose`
- `python hashmap_cli.py compact-snapshot --in snapshots/oct1_demo.pkl.gz --out snapshots/oct1_demo_compacted.pkl.gz --compress || true`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_demo.pkl.gz --repair --out snapshots/oct1_demo_fixed.pkl.gz --verbose`

## oct3_audit.md

```bash
ruff check .
  All checks passed!
```

```bash
mypy src tests
  Success: no issues found in 45 source files
```

```bash
pytest -q
  ...................s...................                                  [100%]
  38 passed, 1 skipped in 82.17s (0:01:22)
```

```bash
python hashmap_cli.py generate-csv --outfile runs/smoke.csv ...
  python hashmap_cli.py --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
  python scripts/validate_metrics_ndjson.py runs/metrics.ndjson
  Validation finished: all lines valid
```
- `python hashmap_cli.py generate-csv --outfile runs/oct3_uniform.csv --ops 5000 --read-ratio 0.75 --key-skew 0.2 --key-space 2000 --seed 103`

```bash
python hashmap_cli.py profile --csv runs/oct3_uniform.csv
  python hashmap_cli.py profile --csv runs/oct3_uniform.csv --then get auditK1
```

```bash
python hashmap_cli.py --mode fast-insert put auditK1 auditV1
  python hashmap_cli.py --mode fast-insert get auditK1
  python hashmap_cli.py --mode fast-lookup put auditK2 auditV2
  python hashmap_cli.py --mode fast-lookup del auditK2
  python hashmap_cli.py --mode adaptive put auditK3 auditV3
  python hashmap_cli.py --mode adaptive items
```

```bash
python hashmap_cli.py run-csv --csv data/workloads/w_uniform.csv --dry-run
  python hashmap_cli.py --json run-csv --csv data/workloads/w_uniform.csv --dry-run
```
- `yes '' | head -n 20 | python hashmap_cli.py config-wizard --outfile runs/oct3_config.toml`

```bash
python hashmap_cli.py --config runs/oct3_config.toml run-csv --csv runs/oct3_uniform.csv \
    --json-summary-out runs/oct3_config_summary.json
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_uniform.csv \
    --metrics-out-dir runs/oct3_metrics \
    --json-summary-out runs/oct3_summary.json \
    --latency-sample-k 500 --latency-sample-every 16
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 --json-summary-out runs/oct3_perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
    --json-summary-out runs/oct3_perf_heavy_adv_noport.json \
    --latency-sample-k 4000 --latency-sample-every 16 \
    --metrics-out-dir runs/oct3_heavy_metrics
```

```bash
python hashmap_cli.py --mode fast-lookup run-csv --csv runs/oct3_uniform.csv \
    --snapshot-out runs/oct3_rh_before.pkl.gz --compress
  python hashmap_cli.py compact-snapshot --in runs/oct3_rh_before.pkl.gz \
    --out runs/oct3_rh_after.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_rh_after.pkl.gz --verbose
```

```bash
python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv \
    --snapshot-out runs/oct3_rh_before2.pkl.gz --compress
  python hashmap_cli.py compact-snapshot --in runs/oct3_rh_before2.pkl.gz \
    --out runs/oct3_rh_after2.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_rh_after2.pkl.gz --verbose
```

```bash
python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv \
    --snapshot-out runs/oct3_chain.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_chain.pkl.gz --verbose
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv \
    --json-summary-out runs/oct3_demo.json \
    --latency-sample-k 1500 --latency-sample-every 40 \
    --snapshot-out runs/oct3_demo.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_demo.pkl.gz --verbose
```

```bash
python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_firsthalf.csv \
     --snapshot-out runs/oct3_snapshot.pkl.gz --compress
```
- `python hashmap_cli.py verify-snapshot --in runs/oct3_snapshot.pkl.gz --verbose`

```bash
python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_secondhalf.csv \
     --snapshot-in runs/oct3_snapshot.pkl.gz \
     --json-summary-out runs/oct3_resumed.json
```
- `python --version`
- `Python 3.11.12`
- `pip list | grep adhash`
- `make lint`
- `make type`
- `make test`
- `make smoke`
- `python hashmap_cli.py -h`
- `python hashmap_cli.py serve -h`
- `python hashmap_cli.py mission-control -h`
- `python scripts/validate_metrics_ndjson.py runs/oct3_metrics/metrics.ndjson`
- `jq '{ops_per_second, final_backend, latency_ms}' runs/oct3_summary.json`
- `python scripts/validate_metrics_ndjson.py runs/oct3_heavy_metrics/metrics.ndjson`
- `jq '{ops_per_second, final_backend}' runs/oct3_perf_heavy_adv_noport.json`
- `ValueError: Bad magic`
- `python -m adhash.batch --spec docs/examples/batch_baseline.toml`
- `python -m adhash.batch --spec docs/examples/batch_compaction.toml`
- `python -m adhash.batch --list`
- `python -m adhash.tui --help`
- `python hashmap_cli.py serve --port 9101 --source runs/oct3_metrics/metrics.ndjson`
- `PermissionError: [Errno 1] Operation not permitted`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 ...`
- `python hashmap_cli.py mission-control`
- `python hashmap_cli.py mission-control -h`

## data_inventory.md

```bash
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
- `python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`
- `python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8`
- `python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10`
- `python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`
- `python hashmap_cli.py generate-csv --outfile data/workloads/hot.csv --ops 200000 --read-ratio 0.10 --key-skew 1.2 --key-space 5000 --adversarial-ratio 0.90 --adversarial-lowbits 8 --seed 42`
- `python hashmap_cli.py generate-csv --outfile data/workloads/stress.csv --ops 200000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 42`
- `python hashmap_cli.py generate-csv --outfile data/workloads/stress_big.csv --ops 600000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 4242`
- `python hashmap_cli.py generate-csv --outfile data/workloads/stress_huge.csv --ops 2000000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 777`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`
- `python -c '...'`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10`
- `python hashmap_cli.py generate-csv --outfile data/workloads/oct1_demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv --snapshot-out snapshots/state.pkl.gz --compress`
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress`
- `python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose`
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_half.csv --snapshot-out snapshots/oct1_state.pkl.gz --compress`
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/oct1_w_skew_adv.csv --snapshot-out snapshots/oct1_rh_before.pkl.gz --compress`
- `python hashmap_cli.py compact-snapshot --in snapshots/oct1_rh_before.pkl.gz --out snapshots/oct1_rh_after.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --repair --out snapshots/oct1_rh_fixed.pkl.gz --verbose`
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/oct1_w_uniform.csv --snapshot-out snapshots/oct1_chain.pkl.gz --compress`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress`
- `python - <<'PY'`
- `HybridAdaptiveHashMap(initial_buckets=8, groups_per_bucket=1)`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --metrics-port 8000 --json-summary-out results/json/run_hot.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_low_threshold.pkl.gz --json-summary-out results/json/run_hot_lowthresh.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_tiny.pkl.gz --json-summary-out results/json/run_hot_tiny.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress.csv --metrics-port 8000 --json-summary-out results/json/run_stress.json`
- `ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress_big.csv --metrics-port 8000 --json-summary-out results/json/run_stress_big_tuned.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress`
- `python -m adhash.tui`
- `python -m adhash.mission_control`

## command_audit.md

```bash
# Headers show gzip + no-store
curl -I --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics

# Probe hist, latency hist, heatmap JSON
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/histogram/latency | jq '.schema, .operations.overall'
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/histogram/probe | jq '.schema, .buckets'
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/heatmap | jq '.schema, .rows, .cols'
```
- `python hashmap_cli.py -h`
- `python hashmap_cli.py config-wizard --outfile config.toml`
- `python hashmap_cli.py config-edit --infile config.toml --outfile runs/oct3_config_edit.toml --save-preset demo --presets-dir runs/presets --force`
- `python hashmap_cli.py ab-compare --csv data/workloads/demo.csv --baseline-config config.toml --candidate-config config.experiment.toml --out-dir results/ab/demo`
- `python hashmap_cli.py --config config.toml run-csv --csv workload.csv`
- `python hashmap_cli.py generate-csv --outfile workload.csv --ops 50000 --read-ratio 0.8`
- `python hashmap_cli.py workload-dna --csv data/workloads/w_uniform.csv --top-keys 8 --pretty`
- `python hashmap_cli.py --mode adaptive put foo bar`
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv`
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A`
- `python hashmap_cli.py --json run-csv --csv data/workloads/w_uniform.csv --dry-run`
- `python hashmap_cli.py run-csv --csv data/workloads/w_uniform.csv --dry-run`
- `python scripts/validate_metrics_ndjson.py runs/metrics.ndjson`
- `make smoke`
- `python hashmap_cli.py mission-control`
- `pytest tests/test_config_wizard.py tests/test_mission_control_widgets_qt.py`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --snapshot-out runs/phase2/adaptive_snapshot.pkl.gz --compress --json-summary-out results/json/phase2_uniform_snapshot.json --latency-sample-k 500 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json`
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress`
- `python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_after.pkl.gz --verbose`
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out runs/phase2/rh_repair_phase2.pkl.gz --verbose`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress`
- `python hashmap_cli.py verify-snapshot --in snapshots/chain.pkl.gz --verbose`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress`
- `ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress_big.csv --metrics-port 8000 --json-summary-out results/json/run_stress_big_tuned.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --metrics-port 8000 --json-summary-out results/json/run_hot.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_low_threshold.pkl.gz --json-summary-out results/json/run_hot_lowthresh.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_tiny.pkl.gz --json-summary-out results/json/run_hot_tiny.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress.csv --metrics-port 8000 --json-summary-out results/json/run_stress.json`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090`
- `--metrics-out-dir runs/phase1`
- `ADHASH_TOKEN=secret python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090`
- `python hashmap_cli.py serve --port 9090 --source runs/metrics.ndjson --follow`
- `python hashmap_cli.py serve --port 9090`
- `ADHASH_TOKEN=secret python hashmap_cli.py serve --host 127.0.0.1 --port 9090`
- `python hashmap_cli.py serve --source results/ab/demo/artifacts/baseline/metrics/metrics.ndjson --compare results/ab/demo/comparison.json`
- `curl --compressed http://127.0.0.1:9090/api/metrics/history.csv?limit=16 -o runs/timeline.csv`
- `curl --compressed http://127.0.0.1:9090/healthz`
- `curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics`
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`
- `ADHASH_TOKEN=secret python hashmap_cli.py mission-control`
- `python hashmap_cli.py mission-control`
- `python hashmap_cli.py mission-control`
- `python -m adhash.batch`
- `pip install -e '.[ui]'`
- `python -m adhash.tui --metrics-endpoint http://127.0.0.1:9090/api/metrics`
- `python -m adhash.batch --spec docs/examples/batch_baseline.toml`
- `python -m adhash.batch --spec docs/examples/batch_compaction.toml`
- `python -m adhash.batch --list`
- `ruff check`
- `mypy src`
- `pytest -q`
- `make lint`
- `make type`
- `make test`
- `make smoke`

## upgrade.md

```bash
Version the schema up front and treat changes as backwards-compatible additions only.

- **Security & Safety Hardening (Early)**
  - Snapshots: keep pickle for now but prepend version + checksum and document “unsafe if untrusted”; schedule a safe binary format (CBOR/Cap’n Proto) decision in Phase 1/2.
  - Dashboard: if exposed beyond localhost, require token/TLS, rate-limit `/api/*`, and bound in-memory buffers/history length.
  - Resource limits: clamp workload file size/row count, latency reservoir length, and dashboard buffer depth; expose overrides but default to safe ceilings.

- **Backward Compatibility Plan**
  - Preserve current CLI commands/flags; introduce new functionality behind additive flags (`--serve`, `repl`). Publish deprecation notices one minor ahead of removal.

- **Performance Budgets**
  - Establish baseline throughput/latency for small/medium/large canonical workloads; capture hardware details. Fail CI or post-merge alerts on >10–15 % regressions.

- **Test Matrix**
  - Required suites: unit (backends, invariants), property-based (Hypothesis for Robin Hood displacement), fuzz CSV ingestion, snapshot round-trip and cross-version compatibility, golden metrics schema tests.
  - Platforms: Linux + macOS runners; Python 3.11 and 3.12 at minimum.
  - Phase-by-phase gating: each phase must expand test coverage to include the features it introduces (see Testing Strategy below).

- **CI Enforcement**
  - Minimal workflow:
```
- `python -m adhash.cli`
- `"schema": "metrics.v1"`
- `make smoke`
- `hashmap_cli.py workload-dna`
- `serve --compare`
- `{"error": "<Code>", "detail": "...", "hint": "..."}`
- `{0 OK, 2 BadInput, 3 Invariant, 4 Policy, 5 IO}`
- `"schema": "metrics.v1"`
- `hashmap-cli --help`
- `schema: "metrics.v1"`
- `ruff --fix`