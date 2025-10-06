# Command Master List

Consolidated unique commands with source docs.

### 1. Sources: audit.md, data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`

### 2. Sources: audit.md

```bash
python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 \
    --adversarial-ratio 0.10 --adversarial-lowbits 8
```

### 3. Sources: audit.md, command_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090`

### 4. Sources: audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv \
    --json-summary-out results/json/perf_uniform.json \
    --latency-sample-k 2000 --latency-sample-every 64
```

### 5. Sources: audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 \
    --json-summary-out results/json/perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
```

### 6. Sources: audit.md

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

### 7. Sources: audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv \
    --snapshot-out snapshots/state.pkl.gz --compress
```

### 8. Sources: audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv \
    --snapshot-in snapshots/state.pkl.gz \
    --json-summary-out results/json/perf_rest.json
```

### 9. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress`

### 10. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress`

### 11. Sources: audit.md, data_inventory.md
`python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose`

### 12. Sources: audit.md

```bash
python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 \
    --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10
```

### 13. Sources: audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
    --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16
```

### 14. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress`

### 15. Sources: audit.md, data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`

### 16. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress`

### 17. Sources: audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --repair --out snapshots/demo_fixed.pkl.gz --verbose`

### 18. Sources: audit.md, command_audit.md, oct1_audit.md, oct3_audit.md
`python hashmap_cli.py -h`

### 19. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode fast-insert put A 1`

### 20. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode fast-lookup get A`

### 21. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive items`

### 22. Sources: audit.md, command_audit.md
`python hashmap_cli.py profile --csv data/workloads/w_uniform.csv`

### 23. Sources: audit.md, command_audit.md
`python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A`

### 24. Sources: audit.md
`cat results/json/perf_uniform.json`

### 25. Sources: audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/state.pkl.gz --verbose`

### 26. Sources: audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --verbose`

### 27. Sources: audit.md, command_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/rh_after.pkl.gz --verbose`

### 28. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode fast-insert put K1 V1`

### 29. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode fast-insert get K1`

### 30. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode fast-lookup put K2 V2`

### 31. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode fast-lookup del K2`

### 32. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive put K3 V3`

### 33. Sources: audit.md, command_audit.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive put foo bar`

### 34. Sources: audit.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive put baz qux`

### 35. Sources: audit.md, command_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/chain.pkl.gz --verbose`

### 36. Sources: audit.md
`# intentionally skip: compact-snapshot on chaining snapshot (should fail)`

### 37. Sources: audit.md
`python hashmap_cli.py profile --csv data/workloads/demo.csv`

### 38. Sources: audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --verbose`

### 39. Sources: audit.md
`python hashmap_cli.py compact-snapshot --in snapshots/demo.pkl.gz --out snapshots/demo_compacted.pkl.gz --compress || true`

### 40. Sources: audit.md, command_audit.md, oct3_audit.md
`make lint`

### 41. Sources: audit.md
`ruff check .`

### 42. Sources: audit.md, command_audit.md, oct3_audit.md
`make type`

### 43. Sources: audit.md
`mypy .`

### 44. Sources: audit.md, command_audit.md, oct3_audit.md
`make test`

### 45. Sources: audit.md, command_audit.md
`pytest -q`

### 46. Sources: audit.md, command_audit.md, oct3_audit.md, upgrade.md
`make smoke`

### 47. Sources: audit.md, command_audit.md
`python scripts/validate_metrics_ndjson.py runs/metrics.ndjson`

### 48. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`

### 49. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`

### 50. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json`

### 51. Sources: audit.md, command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`

### 52. Sources: audit.md, command_audit.md
`python -m adhash.tui --metrics-endpoint http://127.0.0.1:9090/api/metrics`

### 53. Sources: audit.md, command_audit.md
`python hashmap_cli.py serve --port 9090 --source runs/metrics.ndjson --follow`

### 54. Sources: audit.md, command_audit.md, oct3_audit.md
`python -m adhash.batch --spec docs/examples/batch_baseline.toml`

### 55. Sources: audit.md, command_audit.md, oct3_audit.md
`python hashmap_cli.py mission-control`

### 56. Sources: audit.md
`pip install .[gui]`

### 57. Sources: audit.md
`python scripts/query_metric_endpoint.py http://127.0.0.1:9090/api/metrics/histogram/latency operations.overall`

### 58. Sources: audit.md
`python scripts/query_metric_endpoint.py http://127.0.0.1:9090/api/metrics/histogram/probe buckets`

### 59. Sources: audit.md
`curl http://127.0.0.1:9090/api/metrics/heatmap | jq '.rows, .cols, .total'`

### 60. Sources: audit.md
`ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --latency-buckets micro --metrics-port 9090`

### 61. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42`

### 62. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8`

### 63. Sources: oct1_audit.md
`python hashmap_cli.py profile --csv data/workloads/oct1_w_uniform.csv`

### 64. Sources: oct1_audit.md
`python hashmap_cli.py profile --csv data/workloads/oct1_w_uniform.csv --then get A`

### 65. Sources: oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --metrics-port 9091`

### 66. Sources: command_audit.md, data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform.csv --json-summary-out results/json/oct1_perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64`

### 67. Sources: command_audit.md, data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/oct1_perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32`

### 68. Sources: oct1_audit.md
`python -c 'from pathlib import Path; src = Path("data/workloads/oct1_w_uniform.csv").read_text().splitlines(); header, rows = src[0], src[1:]; midpoint = 50_000; Path("data/workloads/oct1_w_uniform_half.csv").write_text("\n".join([header] + rows[:midpoint]) + "\n"); Path("data/workloads/oct1_w_uniform_rest.csv").write_text("\n".join([header] + rows[midpoint:]) + "\n")'`

### 69. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_half.csv --snapshot-out snapshots/oct1_state.pkl.gz --compress`

### 70. Sources: oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_state.pkl.gz --verbose`

### 71. Sources: command_audit.md, data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_uniform_rest.csv --snapshot-in snapshots/oct1_state.pkl.gz --json-summary-out results/json/oct1_perf_rest.json`

### 72. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/oct1_w_skew_adv.csv --snapshot-out snapshots/oct1_rh_before.pkl.gz --compress`

### 73. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py compact-snapshot --in snapshots/oct1_rh_before.pkl.gz --out snapshots/oct1_rh_after.pkl.gz --compress`

### 74. Sources: oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --verbose`

### 75. Sources: oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_after.pkl.gz --verbose`

### 76. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_rh_before.pkl.gz --repair --out snapshots/oct1_rh_fixed.pkl.gz --verbose`

### 77. Sources: oct1_audit.md
`get K1`

### 78. Sources: oct1_audit.md
`put K1 V1`

### 79. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py generate-csv --outfile data/workloads/oct1_w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10`

### 80. Sources: command_audit.md, data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_w_heavy_adv.csv --metrics-port 9101 --json-summary-out results/json/oct1_perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16`

### 81. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/oct1_w_uniform.csv --snapshot-out snapshots/oct1_chain.pkl.gz --compress`

### 82. Sources: oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_chain.pkl.gz --verbose`

### 83. Sources: oct1_audit.md
`python hashmap_cli.py compact-snapshot --in snapshots/oct1_chain.pkl.gz --out snapshots/oct1_chain_compacted.pkl.gz --compress`

### 84. Sources: data_inventory.md, oct1_audit.md
`python hashmap_cli.py generate-csv --outfile data/workloads/oct1_demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7`

### 85. Sources: oct1_audit.md
`python hashmap_cli.py profile --csv data/workloads/oct1_demo.csv`

### 86. Sources: command_audit.md, data_inventory.md, oct1_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/oct1_demo.csv --metrics-port 9092 --json-summary-out results/json/oct1_demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/oct1_demo.pkl.gz --compress`

### 87. Sources: oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_demo.pkl.gz --verbose`

### 88. Sources: oct1_audit.md
`python hashmap_cli.py compact-snapshot --in snapshots/oct1_demo.pkl.gz --out snapshots/oct1_demo_compacted.pkl.gz --compress || true`

### 89. Sources: oct1_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/oct1_demo.pkl.gz --repair --out snapshots/oct1_demo_fixed.pkl.gz --verbose`

### 90. Sources: oct3_audit.md

```bash
ruff check .
  All checks passed!
```

### 91. Sources: oct3_audit.md

```bash
mypy src tests
  Success: no issues found in 45 source files
```

### 92. Sources: oct3_audit.md

```bash
pytest -q
  ...................s...................                                  [100%]
  38 passed, 1 skipped in 82.17s (0:01:22)
```

### 93. Sources: oct3_audit.md

```bash
python hashmap_cli.py generate-csv --outfile runs/smoke.csv ...
  python hashmap_cli.py --mode adaptive run-csv --csv runs/smoke.csv --metrics-out-dir runs
  python scripts/validate_metrics_ndjson.py runs/metrics.ndjson
  Validation finished: all lines valid
```

### 94. Sources: oct3_audit.md
`python hashmap_cli.py generate-csv --outfile runs/oct3_uniform.csv --ops 5000 --read-ratio 0.75 --key-skew 0.2 --key-space 2000 --seed 103`

### 95. Sources: oct3_audit.md

```bash
python hashmap_cli.py profile --csv runs/oct3_uniform.csv
  python hashmap_cli.py profile --csv runs/oct3_uniform.csv --then get auditK1
```

### 96. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode fast-insert put auditK1 auditV1
  python hashmap_cli.py --mode fast-insert get auditK1
  python hashmap_cli.py --mode fast-lookup put auditK2 auditV2
  python hashmap_cli.py --mode fast-lookup del auditK2
  python hashmap_cli.py --mode adaptive put auditK3 auditV3
  python hashmap_cli.py --mode adaptive items
```

### 97. Sources: oct3_audit.md

```bash
python hashmap_cli.py run-csv --csv data/workloads/w_uniform.csv --dry-run
  python hashmap_cli.py --json run-csv --csv data/workloads/w_uniform.csv --dry-run
```

### 98. Sources: oct3_audit.md
`yes '' | head -n 20 | python hashmap_cli.py config-wizard --outfile runs/oct3_config.toml`

### 99. Sources: oct3_audit.md

```bash
python hashmap_cli.py --config runs/oct3_config.toml run-csv --csv runs/oct3_uniform.csv \
    --json-summary-out runs/oct3_config_summary.json
```

### 100. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_uniform.csv \
    --metrics-out-dir runs/oct3_metrics \
    --json-summary-out runs/oct3_summary.json \
    --latency-sample-k 500 --latency-sample-every 16
```

### 101. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 --json-summary-out runs/oct3_perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
```

### 102. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
    --json-summary-out runs/oct3_perf_heavy_adv_noport.json \
    --latency-sample-k 4000 --latency-sample-every 16 \
    --metrics-out-dir runs/oct3_heavy_metrics
```

### 103. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode fast-lookup run-csv --csv runs/oct3_uniform.csv \
    --snapshot-out runs/oct3_rh_before.pkl.gz --compress
  python hashmap_cli.py compact-snapshot --in runs/oct3_rh_before.pkl.gz \
    --out runs/oct3_rh_after.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_rh_after.pkl.gz --verbose
```

### 104. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv \
    --snapshot-out runs/oct3_rh_before2.pkl.gz --compress
  python hashmap_cli.py compact-snapshot --in runs/oct3_rh_before2.pkl.gz \
    --out runs/oct3_rh_after2.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_rh_after2.pkl.gz --verbose
```

### 105. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv \
    --snapshot-out runs/oct3_chain.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_chain.pkl.gz --verbose
```

### 106. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv \
    --json-summary-out runs/oct3_demo.json \
    --latency-sample-k 1500 --latency-sample-every 40 \
    --snapshot-out runs/oct3_demo.pkl.gz --compress
  python hashmap_cli.py verify-snapshot --in runs/oct3_demo.pkl.gz --verbose
```

### 107. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_firsthalf.csv \
     --snapshot-out runs/oct3_snapshot.pkl.gz --compress
```

### 108. Sources: oct3_audit.md
`python hashmap_cli.py verify-snapshot --in runs/oct3_snapshot.pkl.gz --verbose`

### 109. Sources: oct3_audit.md

```bash
python hashmap_cli.py --mode adaptive run-csv --csv runs/oct3_secondhalf.csv \
     --snapshot-in runs/oct3_snapshot.pkl.gz \
     --json-summary-out runs/oct3_resumed.json
```

### 110. Sources: oct3_audit.md
`python --version`

### 111. Sources: oct3_audit.md
`Python 3.11.12`

### 112. Sources: oct3_audit.md
`pip list | grep adhash`

### 113. Sources: oct3_audit.md
`python hashmap_cli.py serve -h`

### 114. Sources: oct3_audit.md
`python hashmap_cli.py mission-control -h`

### 115. Sources: oct3_audit.md
`python scripts/validate_metrics_ndjson.py runs/oct3_metrics/metrics.ndjson`

### 116. Sources: oct3_audit.md
`jq '{ops_per_second, final_backend, latency_ms}' runs/oct3_summary.json`

### 117. Sources: oct3_audit.md
`python scripts/validate_metrics_ndjson.py runs/oct3_heavy_metrics/metrics.ndjson`

### 118. Sources: oct3_audit.md
`jq '{ops_per_second, final_backend}' runs/oct3_perf_heavy_adv_noport.json`

### 119. Sources: oct3_audit.md
`ValueError: Bad magic`

### 120. Sources: command_audit.md, oct3_audit.md
`python -m adhash.batch --spec docs/examples/batch_compaction.toml`

### 121. Sources: command_audit.md, oct3_audit.md
`python -m adhash.batch --list`

### 122. Sources: oct3_audit.md
`python -m adhash.tui --help`

### 123. Sources: oct3_audit.md
`python hashmap_cli.py serve --port 9101 --source runs/oct3_metrics/metrics.ndjson`

### 124. Sources: oct3_audit.md
`PermissionError: [Errno 1] Operation not permitted`

### 125. Sources: oct3_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 ...`

### 126. Sources: data_inventory.md

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

### 127. Sources: data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8`

### 128. Sources: data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10`

### 129. Sources: data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/hot.csv --ops 200000 --read-ratio 0.10 --key-skew 1.2 --key-space 5000 --adversarial-ratio 0.90 --adversarial-lowbits 8 --seed 42`

### 130. Sources: data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/stress.csv --ops 200000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 42`

### 131. Sources: data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/stress_big.csv --ops 600000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 4242`

### 132. Sources: data_inventory.md
`python hashmap_cli.py generate-csv --outfile data/workloads/stress_huge.csv --ops 2000000 --read-ratio 0.10 --key-skew 1.6 --key-space 2048 --adversarial-ratio 0.80 --adversarial-lowbits 12 --seed 777`

### 133. Sources: data_inventory.md
`python -c '...'`

### 134. Sources: data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv --snapshot-out snapshots/state.pkl.gz --compress`

### 135. Sources: data_inventory.md
`python - <<'PY'`

### 136. Sources: data_inventory.md
`HybridAdaptiveHashMap(initial_buckets=8, groups_per_bucket=1)`

### 137. Sources: command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --metrics-port 8000 --json-summary-out results/json/run_hot.json`

### 138. Sources: command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_low_threshold.pkl.gz --json-summary-out results/json/run_hot_lowthresh.json`

### 139. Sources: command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/hot.csv --snapshot-in snapshots/adaptive_tiny.pkl.gz --json-summary-out results/json/run_hot_tiny.json`

### 140. Sources: command_audit.md, data_inventory.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress.csv --metrics-port 8000 --json-summary-out results/json/run_stress.json`

### 141. Sources: command_audit.md, data_inventory.md
`ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/stress_big.csv --metrics-port 8000 --json-summary-out results/json/run_stress_big_tuned.json`

### 142. Sources: data_inventory.md
`python -m adhash.tui`

### 143. Sources: data_inventory.md
`python -m adhash.mission_control`

### 144. Sources: command_audit.md

```bash
# Headers show gzip + no-store
curl -I --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics

# Probe hist, latency hist, heatmap JSON
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/histogram/latency | jq '.schema, .operations.overall'
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/histogram/probe | jq '.schema, .buckets'
curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics/heatmap | jq '.schema, .rows, .cols'
```

### 145. Sources: command_audit.md
`python hashmap_cli.py config-wizard --outfile config.toml`

### 146. Sources: command_audit.md
`python hashmap_cli.py config-edit --infile config.toml --outfile runs/oct3_config_edit.toml --save-preset demo --presets-dir runs/presets --force`

### 147. Sources: command_audit.md
`python hashmap_cli.py ab-compare --csv data/workloads/demo.csv --baseline-config config.toml --candidate-config config.experiment.toml --out-dir results/ab/demo`

### 148. Sources: command_audit.md
`python hashmap_cli.py --config config.toml run-csv --csv workload.csv`

### 149. Sources: command_audit.md
`python hashmap_cli.py generate-csv --outfile workload.csv --ops 50000 --read-ratio 0.8`

### 150. Sources: command_audit.md
`python hashmap_cli.py workload-dna --csv data/workloads/w_uniform.csv --top-keys 8 --pretty`

### 151. Sources: command_audit.md
`python hashmap_cli.py --json run-csv --csv data/workloads/w_uniform.csv --dry-run`

### 152. Sources: command_audit.md
`python hashmap_cli.py run-csv --csv data/workloads/w_uniform.csv --dry-run`

### 153. Sources: command_audit.md
`pytest tests/test_config_wizard.py tests/test_mission_control_widgets_qt.py`

### 154. Sources: command_audit.md
`python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --snapshot-out runs/phase2/adaptive_snapshot.pkl.gz --compress --json-summary-out results/json/phase2_uniform_snapshot.json --latency-sample-k 500 --latency-sample-every 64`

### 155. Sources: command_audit.md
`python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out runs/phase2/rh_repair_phase2.pkl.gz --verbose`

### 156. Sources: command_audit.md
`--metrics-out-dir runs/phase1`

### 157. Sources: command_audit.md
`ADHASH_TOKEN=secret python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090`

### 158. Sources: command_audit.md
`python hashmap_cli.py serve --port 9090`

### 159. Sources: command_audit.md
`ADHASH_TOKEN=secret python hashmap_cli.py serve --host 127.0.0.1 --port 9090`

### 160. Sources: command_audit.md
`python hashmap_cli.py serve --source results/ab/demo/artifacts/baseline/metrics/metrics.ndjson --compare results/ab/demo/comparison.json`

### 161. Sources: command_audit.md
`curl --compressed http://127.0.0.1:9090/api/metrics/history.csv?limit=16 -o runs/timeline.csv`

### 162. Sources: command_audit.md
`curl --compressed http://127.0.0.1:9090/healthz`

### 163. Sources: command_audit.md
`curl --compressed -H "Authorization: Bearer secret" http://127.0.0.1:9090/api/metrics`

### 164. Sources: command_audit.md
`ADHASH_TOKEN=secret python hashmap_cli.py mission-control`

### 165. Sources: command_audit.md
`python -m adhash.batch`

### 166. Sources: command_audit.md
`pip install -e '.[ui]'`

### 167. Sources: command_audit.md
`ruff check`

### 168. Sources: command_audit.md
`mypy src`

### 169. Sources: upgrade.md

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

### 170. Sources: upgrade.md
`python -m adhash.cli`

### 171. Sources: upgrade.md
`"schema": "metrics.v1"`

### 172. Sources: upgrade.md
`hashmap_cli.py workload-dna`

### 173. Sources: upgrade.md
`serve --compare`

### 174. Sources: upgrade.md
`{"error": "<Code>", "detail": "...", "hint": "..."}`

### 175. Sources: upgrade.md
`{0 OK, 2 BadInput, 3 Invariant, 4 Policy, 5 IO}`

### 176. Sources: upgrade.md
`hashmap-cli --help`

### 177. Sources: upgrade.md
`schema: "metrics.v1"`

### 178. Sources: upgrade.md
`ruff --fix`
