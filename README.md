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
- `docs/config.md` – TOML configuration schema and usage instructions.

## Requirements & Support Policy

- **Python:** 3.11 or 3.12 (our CI matrix mirrors this; earlier versions are unsupported).
- **Shell:** POSIX-like (macOS/Linux). PowerShell users should replace `\` line continuations with backticks or run commands on a single line.
- **Ports:** Local access when using the built-in metrics dashboard (default ports 9090/9091/9100). If your sandbox blocks port binding, run with elevated permissions.

### Release Cadence & Targets

- **Cadence:** Monthly tagged release (or ad hoc for major feature drops) with refreshed `audit.md` artifacts.
- **Performance guardrail:** Smoke workload (`make smoke`, 2k ops) should stay within ±15% of the recorded baseline (~20k ops/s on Apple M2 Pro, captured 2025-10-01). Regressions must include updated benchmarks.
- **Non-goals:** Distributed deployment, multi-tenant workload serving, and production-grade dashboard auth. Keep the dashboard bound to localhost or front it with your own proxy if exposure is required.

## Quick Start

To customise adaptive behaviour, provide a TOML config via `--config` (see [`docs/config.md`](docs/config.md)). Environment variables such as `ADAPTIVE_START_BACKEND` are still honoured but the TOML file is now the canonical format.

```bash
python hashmap_cli.py config-wizard --outfile config.toml  # interactive generator for config TOML
python hashmap_cli.py --config config.toml run-csv --csv workload.csv
```

```bash
python hashmap_cli.py -h                       # explore available subcommands
python hashmap_cli.py --mode adaptive put K V  # single operation using adaptive backend
python hashmap_cli.py generate-csv --outfile workload.csv --ops 50000 --read-ratio 0.8
python hashmap_cli.py profile --csv workload.csv
python hashmap_cli.py --mode adaptive run-csv --csv workload.csv --json-summary-out perf.json --metrics-max-ticks 500
```

Need machine-readable output for automation? Add `--json` to emit success envelopes:

```bash
python hashmap_cli.py --json run-csv --csv workload.csv --dry-run
```

Need to sanity-check a workload before running it?

```bash
python hashmap_cli.py run-csv --csv workload.csv --dry-run
```

## Phase 0–2 Command Index

The upgrade roadmap lives in [`upgrade.md`](upgrade.md). This index summarises the commands verified while completing Phases 0–2; see [`audit.md`](audit.md) and [`oct1_audit.md`](oct1_audit.md) for the full transcripts and artifacts.

### Phase 0 – Strategy & Baseline Hardening
- `make setup` – bootstrap the dev environment (`pip install -e .[dev]`, run once per clone; requires network access).
- `make lint` – run `ruff check .` (lint gate).
- `make type` – run `mypy .` (type gate).
- `make test` – run `pytest -q` (unit, property, CLI contract, and snapshot tests).
- `make smoke` – generate `runs/smoke.csv`, replay it with `--metrics-out-dir runs`, and validate `runs/metrics.ndjson`.
- `python scripts/validate_metrics_ndjson.py runs/metrics.ndjson` – standalone schema validator (also invoked by `make smoke`).

### Phase 1 – Reliability, Observability & Safety
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` – baseline JSON summary with latency sampling (Audit Step 4).
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_skew_adv.csv --compact-interval 2.0 --json-summary-out results/json/perf_skew_adv.json --latency-sample-k 3000 --latency-sample-every 32` – proactive compaction tick (Audit Step 5).
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform_rest.csv --snapshot-in snapshots/state.pkl.gz --json-summary-out results/json/perf_rest.json` – resume from adaptive snapshot (Audit Step 6).
- `python hashmap_cli.py --mode fast-lookup run-csv --csv data/workloads/w_skew_adv.csv --snapshot-out snapshots/rh_before.pkl.gz --compress` → `python hashmap_cli.py compact-snapshot --in snapshots/rh_before.pkl.gz --out snapshots/rh_after.pkl.gz --compress` → `python hashmap_cli.py verify-snapshot --in snapshots/rh_after.pkl.gz --verbose` – Robin Hood offline compaction (Audit Step 7).
- `python hashmap_cli.py verify-snapshot --in snapshots/rh_before.pkl.gz --repair --out snapshots/rh_fixed.pkl.gz --verbose` – safe repair path (Audit Step 8).
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv --metrics-port 9100 --json-summary-out results/json/perf_heavy_adv.json --latency-sample-k 4000 --latency-sample-every 16` – adversarial stress with live metrics (Audit Step 10).
- `python hashmap_cli.py --mode fast-insert run-csv --csv data/workloads/w_uniform.csv --snapshot-out snapshots/chain.pkl.gz --compress` → `python hashmap_cli.py verify-snapshot --in snapshots/chain.pkl.gz --verbose` – failure-path coverage (Audit Step 12).

### Phase 2 – User Interfaces & Workflow Enhancements
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv` – quick backend recommendation (Audit Step 2).
- `python hashmap_cli.py profile --csv data/workloads/w_uniform.csv --then get A` – profile and immediately exercise a lookup (Audit Step 2 follow-up).
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090` – Plotly dashboard + Prometheus endpoint (Audit Step 3).
- `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --json-summary-out results/json/perf_uniform.json --latency-sample-k 2000 --latency-sample-every 64` – JSON summary while the dashboard is live (Audit Step 4).
- `python hashmap_cli.py --mode adaptive put foo bar` / `get foo` / `items` – one-shot CLI smoke (Audit Step 11).
- `python -m adhash.tui --metrics-endpoint http://127.0.0.1:9090/api/metrics` – interactive Textual TUI (install with `pip install .[ui]`).
- `python hashmap_cli.py serve --port 9090 --source runs/metrics.ndjson --follow` – sticky dashboard server fed by NDJSON metrics.
- `python -m adhash.batch --spec docs/examples/batch_baseline.toml` – batch benchmark runner generating Markdown reports.
- `python hashmap_cli.py mission-control` – launches the PyQt6 Mission Control shell (install with `pip install .[gui]`).
- Demo flow: `python hashmap_cli.py generate-csv --outfile data/workloads/demo.csv --ops 80000 --read-ratio 0.7 --key-skew 1.1 --key-space 15000 --seed 1 --adversarial-ratio 0.15 --adversarial-lowbits 7` → `python hashmap_cli.py profile --csv data/workloads/demo.csv` → `python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/demo.csv --metrics-port 9091 --json-summary-out results/json/demo_perf.json --latency-sample-k 1500 --latency-sample-every 40 --snapshot-out snapshots/demo.pkl.gz --compress` (Audit One-shot Demo).

### Metrics Dashboard & Prometheus Endpoint

```bash
python hashmap_cli.py --mode adaptive run-csv --csv workload.csv --metrics-port 9090
```

- Dashboard: `http://localhost:9090/` (Plotly charts with zoom/pan, histograms/heatmaps, and live alert banners)
- Metrics: `http://localhost:9090/metrics`
- Metrics JSON: `http://localhost:9090/api/metrics` (latest tick, powers dashboard/API consumers)
- Metrics history: `http://localhost:9090/api/metrics/history?limit=100` (recent ticks when retention enabled)
- Latency histogram (JSON): `http://localhost:9090/api/metrics/histogram/latency`
- Probe histogram (JSON): `http://localhost:9090/api/metrics/histogram/probe`
- Key distribution heatmap (JSON): `http://localhost:9090/api/metrics/heatmap`
- Ultra-fast runs? Add `--latency-buckets micro` to `run-csv` for sub-ms latency bins (pairs well with Textual/Plotly views).

Counters include total ops/puts/gets/dels, migrations, compactions, and gauges for load factor, max chaining group length, average Robin Hood probe distance, plus an identifying backend label. The updated dashboard surfaces those metrics alongside throughput, guardrail alerts, latency histograms, probe-length bar charts, and a key-distribution heatmap powered by the new JSON endpoints.

Note: the tombstone ratio plot only populates when the RobinHood backend is active and tombstones exist. Workloads that stay on chaining (or never issue deletes) will keep that series near zero. To exercise the chart, try a workload that forces the adaptive map onto RobinHood (e.g. `runs/audit_w_skew_adv.csv` or any heavy-delete CSV) or run `run-csv` in `--mode fast-lookup` with deletes enabled.

For Prometheus/Grafana setup, import dashboards, and example alert rules, see [`docs/prometheus_grafana.md`](docs/prometheus_grafana.md).

### Terminal TUI (Textual)

Prefer the terminal? Install the optional UI extras and launch the Textual dashboard:

```bash
pip install .[ui]
python -m adhash.tui --metrics-endpoint http://127.0.0.1:9090/api/metrics
```

The TUI polls the JSON endpoint exposed by `hashmap_cli.py --metrics-port …`, summarises backend state, operation counts, guardrail alerts, and latency percentiles, and refreshes every few seconds. Press `r` to force a refresh or `q` to exit.
Version ≥Phase‑2 adds a rolling history panel that reports recent load-factor samples, throughput (ops/s), and cumulative migrations.
Recent migration/compaction events are now surfaced as a live list (also available via `http://HOST:PORT/api/events`).

### Batch Benchmark Runner (TOML)

Define suites of workloads in a TOML spec and run them with a single command:

```bash
python -m adhash.batch --spec docs/examples/batch_baseline.toml
```

This executes each job sequentially, writes any requested JSON summaries, and produces Markdown (and optional HTML) reports (see [`docs/batch_runner.md`](docs/batch_runner.md)). Specs support `profile` and `run-csv` jobs, latency sampling controls, metrics output directories, and arbitrary extra CLI arguments. Use the generated report to diff throughput/backends across workloads without manually replaying each command.

### Sticky Serve Mode

Keep the dashboard alive independently of a workload run and optionally replay NDJSON metrics:

```bash
python hashmap_cli.py serve --port 9090 --source runs/metrics.ndjson --follow

# In another shell generate metrics ticks
python hashmap_cli.py --mode adaptive run-csv \
  --csv data/workloads/w_uniform.csv \
  --metrics-out-dir runs
```

`serve` starts the HTTP dashboard/metrics API and, when `--source` is provided, preloads the NDJSON ticks (schema `metrics.v1`). With `--follow` it tails the file so the dashboard updates while `run-csv` appends new metrics. Skip `--source` to launch an empty dashboard for ad-hoc monitoring; press `Ctrl+C` to stop.

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

1. Ensure Python 3.11+ is installed and you are in the repository root.
2. Run through [`audit.md`](#auditmd), checking each item. The file already lists the commands with proper line continuations.
3. For steps that bind HTTP ports, run with appropriate privileges if your environment blocks low-numbered or privileged ports.
4. Verify that CSV/JSON/snapshot outputs match expectations (names are hard-coded in the checklist so results overwrite existing artifacts).

## Testing & Automation

- `pytest -q` – full unit/property/contract suite (includes snapshot and CLI error-envelope coverage).
- `pytest tests/test_perf_smoke.py -q` – lightweight regression that replays 200 ops and checks throughput plus `metrics.v1` ticks.
- `make smoke` – generate a small workload, replay it with metrics, and validate the emitted NDJSON via `scripts/validate_metrics_ndjson.py`.

All commands assume you have installed dev dependencies via `make setup` (see [`CONTRIBUTING.md`](CONTRIBUTING.md)).

## Additional Notes

- Per-op latency reservoirs are on by default whenever `--json-summary-out` is provided; to reduce overhead you can raise `--latency-sample-every` or set `--latency-sample-k 0` to disable sampling.
- The dashboards rely on Plotly via CDN; require outbound network access if you open them in a browser.
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

Alerts use the same configuration surface. The watchdog emits warnings (log + dashboard banner) when metrics cross guardrails; adjust or disable it via:

```bash
WATCHDOG_ENABLED=false \
WATCHDOG_LOAD_FACTOR_WARN=0.95 \
WATCHDOG_TOMBSTONE_WARN=0.40 \
  python hashmap_cli.py run-csv --csv workloads/hot.csv --metrics-port 8000
```

Setting a threshold to `"none"` in a TOML config disables that specific guardrail while keeping the others active.

## Status & Next Steps

- **Production-ready today.** Snapshot serialization hardened, metrics hooks reattached after load, metrics server lifecycle wrapped in `try/finally` + `server_close()`.
- **Next up:** C++ port using the same snapshot binary spec (`Adaptive HMAP v1`) so we can benchmark native throughput and keep cross-language compatibility.
- **Integration roadmap:** publish the binary snapshot schema, wire metrics into Grafana/Prometheus exporters, add JSONL streaming, and let CI pipelines diff latencies across implementations.
- **Learning track:** explore the [`audit.md`](#auditmd) demo flow for a quick “generate → profile → run → snapshot → verify → repair” walkthrough, then plug in the forthcoming C++ reader once available.

Contributions or experiments should update [`audit.md`](#auditmd) with new scenarios and attach fresh artifacts so future auditors can reproduce and benchmark the same paths.
