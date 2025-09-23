# Adaptive Hash Map CLI
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](#) [![Tested](https://img.shields.io/badge/tests-passed-brightgreen)](#) [![Docs](https://img.shields.io/badge/docs-available-blueviolet)](#)
*AdaptiveHashMapCLI is a teaching and benchmarking tool that turns abstract data structures into live, measurable systems.*

[`hashmap_cli.py`](#hashmap_clipy) is a batteries-included command-line harness for exploring and validating three hash-map backends:

- `TwoLevelChainingMap` – cache-friendly two-level chaining tuned for heavy writes.
- `RobinHoodMap` – open addressing with tombstone-aware Robin Hood displacement.
- `HybridAdaptiveHashMap` – automatically migrates between chaining and Robin Hood based on live health metrics.

The toolset covers workload generation, profiling, CSV replays with live metrics, latency sampling, snapshot/restore flows (with safe repairs), and verification utilities. Everything ships in a single Python file so you can drop it into pipelines or run ad-hoc tests without extra dependencies.

## Repo Contents

- `hashmap_cli.py` – main CLI and data-structure implementations.
- `audit.md` – step-by-step validation checklist (all commands verified in the latest audit and boxes checked).
- `data/` – reusable assets (`workloads/` holds generated CSV workloads; `config/` contains demo overrides).
- `results/json/` – JSON summaries produced by all recorded runs (perf benchmarks, stress tests, dashboard demos).
- `snapshots/` – serialized map states referenced in the audit (Robin Hood compaction, adaptive resume, etc.).
- `docs/data_inventory.md` – file tree with per-artifact explanations and which test produced each file.

## Requirements

- Python 3.9+ (tested with CPython 3.10).
- POSIX-like shell (macOS/Linux). PowerShell users should replace `\` line continuations with backticks or single-line commands.
- Local port access when using the built-in metrics dashboard (default ports 9090/9091/9100). If your sandbox restricts binding ports, run the commands with elevated permissions.

## Quick Start

```bash
python hashmap_cli.py -h                       # explore available subcommands
python hashmap_cli.py --mode adaptive put K V  # single operation using adaptive backend
python hashmap_cli.py generate-csv --outfile workload.csv --ops 50000 --read-ratio 0.8
python hashmap_cli.py profile --csv workload.csv
python hashmap_cli.py --mode adaptive run-csv --csv workload.csv --json-summary-out perf.json
```

### Metrics Dashboard & Prometheus Endpoint

```bash
python hashmap_cli.py --mode adaptive run-csv --csv workload.csv --metrics-port 9090
```

- Dashboard: `http://localhost:9090/`
- Metrics: `http://localhost:9090/metrics`

Counters include total ops/puts/gets/dels, migrations, compactions, and gauges for load factor, max chaining group length, average Robin Hood probe distance, plus an identifying backend label.

## Validation Checklist

Comprehensive end-to-end coverage lives in **[`audit.md`](#auditmd)**. It is organized into 12 sections plus an optional “demo” flow:

1. CLI sanity checks.
2. Workload generation (uniform, skewed, adversarial).
3. CSV profiling to recommend backends.
4. CSV replays with live metrics, JSON summaries, and per-op latency reservoirs.
5. Proactive compaction ticks.
6. Snapshot save/load/continue workflows (including verifying and resuming from snapshots).
7. Offline compaction for RobinHood snapshots.
8. Safe repair path for corrupted RobinHood snapshots.
9. One-shot smoke tests across all modes.
10. Adversarial stress workload with metrics streaming.
11. Minimal interactive smoke checks.
12. Failure-path verification (ensures compaction refuses incompatible snapshots).
13. Optional “everything in one go” demo.

All items were executed successfully on 2025-09-22; checkmarks in [`audit.md`](#auditmd) reflect the exact commands run and artifacts produced. Step 6 notes that when splitting CSV files manually, you must keep the header row (`op,key,value`).

## Recent Audit Results

| Workload | Ops | Mode | Ops/s | Backend at Finish | p99 Latency (ms, overall) | JSON Summary |
|----------|-----|------|-------|-------------------|---------------------------|--------------|
| `w_uniform.csv` | 100k | adaptive | ~2.28k | chaining | 3.35 | [`results/json/perf_uniform.json`](results/json/perf_uniform.json) |
| `w_skew_adv.csv` | 100k | adaptive | ~3.34k | chaining | 1.68 | [`results/json/perf_skew_adv.json`](results/json/perf_skew_adv.json) |
| `w_uniform_rest.csv` (resume) | 50k | adaptive | ~1.47k | chaining | 4.13 | [`results/json/perf_rest.json`](results/json/perf_rest.json) |
| `w_heavy_adv.csv` | 200k | adaptive | ~2.54k | chaining | 0.89 | [`results/json/perf_heavy_adv.json`](results/json/perf_heavy_adv.json) |
| `demo.csv` (full demo) | 80k | adaptive | ~5.25k | chaining | 0.86 | [`results/json/demo_perf.json`](results/json/demo_perf.json) |

Observations:

- Throughput ranges from ~1.5k to ~5.2k ops/s for the Python implementation on a single core, increasing with workload locality. These numbers align with expectations for a pure-Python, single-threaded benchmark.
- No adaptive migrations or compactions were triggered under the audited workloads; load factors and probe estimates stayed within configured guardrails.
- Per-op latency reservoirs captured GET sub-millisecond response times and PUT/DEL latencies in the ~0.8–3.4 ms range depending on load.
- Safety features verified: snapshots serialize without callback issues, Robin Hood repair paths compact tombstones, and `compact-snapshot` correctly rejects non-RobinHood inputs.

## Snapshot Safety & Metrics Hooks

Snapshots now store a callback-free state. On load (including direct pickle usage), `HybridAdaptiveHashMap.__setstate__` rebuilds a fresh `AdaptiveConfig`. Runtime callbacks for metrics are reattached automatically by `_reattach_runtime_callbacks`, ensuring migrations/compactions continue to update counters even when starting from restored snapshots.

## Reproducing the Audit

1. Ensure Python 3.9+ is installed and you are in the repository root.
2. Run through [`audit.md`](#auditmd), checking each item. The file already lists the commands with proper line continuations.
3. For steps that bind HTTP ports, run with appropriate privileges if your environment blocks low-numbered or privileged ports.
4. Verify that CSV/JSON/snapshot outputs match expectations (names are hard-coded in the checklist so results overwrite existing artifacts).

## Additional Notes

- Per-op latency reservoirs are on by default whenever `--json-summary-out` is provided; to reduce overhead you can raise `--latency-sample-every` or set `--latency-sample-k 0` to disable sampling.
- The dashboards rely on `Chart.js` via CDN; require outbound network access if you open them in a browser.
- `compact-snapshot` intentionally refuses non-RobinHood snapshots (as seen in the demo flow) to avoid corrupting incompatible formats.

### Forcing an Adaptive Migration (to light up the APE chart)

The adaptive wrapper only migrates when chaining trips its health limits. Under many workloads it happily stays in chaining—`ape` stays at 0 and `hashmap_migrations_total` never increments. To demonstrate the Robin Hood leg:

```bash
# 1) Generate a highly adversarial, write-heavy workload
python hashmap_cli.py generate-csv \
  --outfile stress.csv \
  --ops 200000 \
  --read-ratio 0.10 \
  --key-skew 1.6 \
  --key-space 2048 \
  --adversarial-ratio 0.80 \
  --adversarial-lowbits 12 \
  --seed 42

# 2) (Optional) temporarily tighten thresholds in build_map()
#    max_lf_chaining = 0.55   # below the chaining rehash at 0.80
#    max_group_len   = 2

# 3) Replay with metrics enabled
python hashmap_cli.py --mode adaptive run-csv \
  --csv stress.csv \
  --metrics-port 8000 \
  --json-summary-out run_stress.json
```

Watch `http://localhost:8000/` during the run: the backend label flips to `chaining -> robinhood (migrating)` and `ape` starts plotting non-zero values once Robin Hood takes over. `hashmap_migrations_total` in `/metrics` and the JSON summary will increment accordingly. If you only want to visualise probe distances, run the same CSV with `--mode fast-lookup` to stay on RobinHoodMap from the start.

#### Threshold overrides without code edits

Prefer not to touch the source? Use environment variables to tighten the adaptive thresholds for a single run:

```bash
ADAPTIVE_MAX_LF_CHAINING=0.55 ADAPTIVE_MAX_GROUP_LEN=2 \
  python hashmap_cli.py --mode adaptive run-csv \
    --csv data/workloads/stress_big.csv \
    --metrics-port 8000 \
    --json-summary-out results/json/run_stress_big_tuned.json
```

With these overrides the workload triggers migrations immediately. The latest audit captured `results/json/run_stress_big_tuned.json` (600k ops, three migrations, sustained throughput ~43k ops/s). Keep the CLI running while you open `http://localhost:8000/`; you’ll see the backend label toggle and the `ape` chart populate in real time.

## Status & Next Steps

- **Production-ready today.** Snapshot serialization hardened, metrics hooks reattached after load, metrics server lifecycle wrapped in `try/finally` + `server_close()`.
- **Next up:** C++ port using the same snapshot binary spec (`Adaptive HMAP v1`) so we can benchmark native throughput and keep cross-language compatibility.
- **Integration roadmap:** publish the binary snapshot schema, wire metrics into Grafana/Prometheus exporters, add JSONL streaming, and let CI pipelines diff latencies across implementations.
- **Learning track:** explore the [`audit.md`](#auditmd) demo flow for a quick “generate → profile → run → snapshot → verify → repair” walkthrough, then plug in the forthcoming C++ reader once available.

Contributions or experiments should update [`audit.md`](#auditmd) with new scenarios and attach fresh artifacts so future auditors can reproduce and benchmark the same paths.
