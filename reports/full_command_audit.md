# Full Command Audit

Started: 2025-10-04T23:18:10.950350

## 2025-10-04T23:18:23 python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42
- ✅ Wrote workload CSV: data/workloads/w_uniform.csv

## 2025-10-04T23:18:46 python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 --adversarial-ratio 0.10 --adversarial-lowbits 8
- ✅ Wrote workload CSV: data/workloads/w_skew_adv.csv

## 2025-10-04T23:19:08 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090
- ⚠️ Failed: PermissionError binding port 9090 in sandbox (requires elevated privileges).

## 2025-10-04T23:19:29 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64 --metrics-port 9090
- ⚠️ Failed: PermissionError binding port 9090 (sandbox limitation).

## 2025-10-04T23:19:49 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32 --metrics-port 9090
- ⚠️ Failed: PermissionError binding port 9090 (sandbox).

## 2025-10-04T23:20:12 Python split workload script
- ✅ Generated data/workloads/w_uniform_half.csv and data/workloads/w_uniform_rest.csv

## 2025-10-04T23:21:16 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv --snapshot-out snapshots/state.pkl.gz --compress
- ✅ Completed in ~19.6s, snapshot saved to snapshots/state.pkl.gz

## 2025-10-04T23:22:38 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json
- ✅ Completed in ~57s, summary written to results/json/perf_rest.json

## 2025-10-04T23:23:04 python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress
- ✅ Completed in ~0.18s, snapshot saved to snapshots/rh_before.pkl.gz

## 2025-10-04T23:23:26 python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress
- ✅ Compaction succeeded; output snapshots/rh_after.pkl.gz

## 2025-10-04T23:23:43 python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose
- ✅ Snapshot verified and repaired; output snapshots/rh_fixed.pkl.gz

## 2025-10-04T23:24:14 python hashmap_cli.py generate-csv --outfile data/workloads/w_heavy_adv.csv --ops 200000 --read-ratio 0.4 --key-skew 1.4 --key-space 50000 --seed 777 --adversarial-ratio 0.25 --adversarial-lowbits 10
- ✅ Wrote workload CSV: data/workloads/w_heavy_adv.csv

## 2025-10-04T23:24:36 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16
- ⚠️ Failed: PermissionError binding port 9100 (sandbox).

## 2025-10-04T23:25:06 python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress
- ✅ Snapshot written to snapshots/chain.pkl.gz

## 2025-10-04T23:25:32 python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7
- ✅ Wrote workload CSV: data/workloads/demo.csv

## 2025-10-04T23:25:53 python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress
- ⚠️ Failed: PermissionError binding port 9091 (sandbox).

## 2025-10-04T23:26:14 python hashmap_cli.py verify-snapshot --in snapshots/demo.pkl.gz --repair --out snapshots/demo_fixed.pkl.gz --verbose
- ⚠️ Failed: snapshot missing (previous run-csv aborted due to port bind); command returned Invariant error.

## 2025-10-04T23:26:33 python hashmap_cli.py -h
- ✅ Displayed CLI help.

## 2025-10-04T23:26:41 python hashmap_cli.py --mode fast-insert put A 1
- ✅ Output: OK

## 2025-10-04T23:26:46 python hashmap_cli.py --mode fast-lookup get A
- ✅ Returned value printed to stdout (blank means key missing).

## 2025-10-04T23:28:08 python hashmap_cli.py --mode adaptive items
- ✅ Command executed (no items to display).

## 2025-10-04T23:57:54 (audit.md, data_inventory.md)
```bash
python hashmap_cli.py generate-csv --outfile data/workloads/w_uniform.csv --ops 100000 --read-ratio 0.8 --key-skew 0.0 --key-space 20000 --seed 42
```
- exit code: 0
- stderr:
```
2025-10-04T23:57:54 [INFO] hashmap_cli: Wrote workload CSV: data/workloads/w_uniform.csv
```

## 2025-10-04T23:57:54 (audit.md)
```bash
python hashmap_cli.py generate-csv --outfile data/workloads/w_skew_adv.csv --ops 100000 --read-ratio 0.6 --key-skew 1.2 --key-space 20000 --seed 1337 \
    --adversarial-ratio 0.10 --adversarial-lowbits 8
```
- exit code: 0
- stderr:
```
2025-10-04T23:57:54 [INFO] hashmap_cli: Wrote workload CSV: data/workloads/w_skew_adv.csv
```

## 2025-10-04T23:57:54 (audit.md, command_audit.md)
```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090
```
- exit code: 4
- stderr:
```
Unhandled CLI exception
Traceback (most recent call last):
  File "/Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/src/adhash/contracts/error.py", line 91, in _wrapped
    return fn(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^
  File "/Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/src/adhash/cli/commands.py", line 246, in handler
    result = ctx.run_csv(
             ^^^^^^^^^^^^
  File "/Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/hashmap_cli.py", line 636, in run_csv
    server, stop_server = start_metrics_server(metrics, metrics_port)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/src/adhash/metrics/server.py", line 403, in start_metrics_server
    server = HTTPServer((host, port), Handler)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/homebrew/Cellar/python@3.11/3.11.13_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/socketserver.py", line 456, in __init__
    self.server_bind()
  File "/opt/homebrew/Cellar/python@3.11/3.11.13_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/http/server.py", line 136, in server_bind
    socketserver.TCPServer.server_bind(self)
  File "/opt/homebrew/Cellar/python@3.11/3.11.13_1/Frameworks/Python.framework/Versions/3.11/lib/python3.11/socketserver.py", line 472, in server_bind
    self.socket.bind(self.server_address)
PermissionError: [Errno 1] Operation not permitted
{"error": "Unhandled", "detail": "PermissionError: [Errno 1] Operation not permitted"}
```

## 2025-10-04T23:57:55 (audit.md)
```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv \
    --json-summary-out results/json/perf_uniform.json \
    --latency-sample-k 2000 --latency-sample-every 64
```
- exit code: 0
- stderr:
```
2025-10-04T23:57:55 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-04T23:59:11 [INFO] hashmap_cli: run-csv finished in 75.958168 s, backend=chaining
2025-10-04T23:59:11 [INFO] hashmap_cli: Wrote JSON summary: results/json/perf_uniform.json
```

## 2025-10-05T00:00:17 (audit.md)
```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv \
    --compact-interval 2.0 \
    --json-summary-out results/json/perf_skew_adv.json \
    --latency-sample-k 3000 --latency-sample-every 32
```
- exit code: 0
- stderr:
```
2025-10-05T00:00:17 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-05T00:01:10 [INFO] hashmap_cli: run-csv finished in 52.459539 s, backend=chaining
2025-10-05T00:01:10 [INFO] hashmap_cli: Wrote JSON summary: results/json/perf_skew_adv.json
```

## 2025-10-05T00:01:10 (audit.md)
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
- exit code: 1
- stderr:
```
File "<stdin>", line 1
    from pathlib import Path
IndentationError: unexpected indent
```

## 2025-10-05T00:01:10 (audit.md)
```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_half.csv \
    --snapshot-out snapshots/state.pkl.gz --compress
```
- exit code: 0
- stderr:
```
2025-10-05T00:01:10 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-05T00:01:30 [INFO] hashmap_cli: run-csv finished in 20.311701 s, backend=chaining
2025-10-05T00:01:30 [INFO] hashmap_cli: Wrote snapshot to snapshots/state.pkl.gz (compress=True)
```
