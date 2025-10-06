# Adaptive Hash Map CLI

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](#requirements) [![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](#validation) [![Docs](https://img.shields.io/badge/docs-updated-blueviolet)](#documentation)
[![Mission Control](https://img.shields.io/badge/mission_control-PyQt6-orange)](#mission-control-pyqt6) [![Terminal TUI](https://img.shields.io/badge/terminal_tui-Textual-ff69b4)](#textual-tui-terminal) [![Snapshots](https://img.shields.io/badge/snapshots-versioned%20%2B%20checksummed-success)](#snapshots--configuration)

AdaptiveHashMapCLI is an end-to-end playground for modern hash map design. It packages production-ready data structures, CSV-driven workload tooling, automated benchmarks, and rich UIs (PyQt6 Mission Control + Textual TUI) into a single repository. Every feature is exercised through lint/type/test gates and captured in reproducible audits.

> **Work in progress**: Phase 0–2 are complete and thoroughly audited; Phase 3 (deployment & integration) is underway. Expect frequent updates as we continue hardening the platform.

Key capabilities include:

- Three map backends (two-level chaining, Robin Hood, adaptive hybrid) with live migration and guardrails.
- CSV workload generator, profiler, and replay engine with latency reservoirs, JSON summaries, and metrics streaming.
- Snapshot lifecycle: save/load, versioned header + checksum, offline compaction and safe repair.
- Mission Control desktop app featuring telemetry charts, config editor, benchmark suite manager, workload DNA explorer, and a new snapshot inspector with historical replay controls.
- Textual TUI for terminal dashboards, batch benchmark runner, Prometheus-compatible metrics server, and `inspect-snapshot` CLI inspections.

Everything in this README is current as of the latest audit (October 2025).

---

## Requirements

- **Python**: 3.11 or 3.12 (we test against both). Python 3.9/3.10 are no longer supported.
- **OS**: macOS or Linux shell. Windows users should work inside WSL2.
- **Optional extras**:
  - `PyQt6`, `pyqtgraph`, `numpy` for Mission Control (`pip install .[gui]`).
  - `textual`, `rich` for the terminal dashboard (`pip install .[ui]`).
  - Prometheus / Grafana if you plan to ingest `/metrics` output.

Install everything for development:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .[dev,gui,ui]
```

---

## Quick Start

1. **Generate a config** (TOML is the canonical format):

   ```bash
   python hashmap_cli.py config-wizard --outfile config.toml
   ```

2. **Dry-run a workload** to catch CSV issues without executing it:

   ```bash
   python hashmap_cli.py run-csv --csv data/workloads/demo.csv --dry-run
   ```

3. **Replay with metrics + JSON summary**:

   ```bash
   python hashmap_cli.py --config config.toml run-csv \
     --csv data/workloads/demo.csv \
     --json-summary-out results/json/demo_metrics_session.json \
     --metrics-out-dir runs/metrics_demo
   ```

4. **Launch Mission Control** to inspect metrics, snapshots, and configs:

   ```bash
   python hashmap_cli.py mission-control
   ```

5. **Sanity-check snapshots** from the CLI or GUI:

   ```bash
   python hashmap_cli.py inspect-snapshot --in snapshots/uniform.pkl.gz --limit 10
   ```

6. **Run the regression suite** (all must pass before pushing):

   ```bash
   make lint
   make type
   make test
   ```

All three commands are logged in `reports/command_run_log.tsv` along with the full async audit transcripts.

---

## Hands-On Walkthrough

The following mini-tour lets you experience every major feature with real commands. Feel free to copy/paste line-by-line.

### 1. Generate & profile workloads

```bash
# Step 1A: create a config and adjust thresholds quickly
python hashmap_cli.py config-wizard --outfile runs/demo_config.toml

# Step 1B: generate workloads with different access patterns
mkdir -p runs/workloads
python hashmap_cli.py generate-csv --outfile runs/workloads/w_uniform.csv --ops 50000 --read-ratio 0.8 --seed 7
python hashmap_cli.py generate-csv --outfile runs/workloads/w_skew_adv.csv --ops 50000 --read-ratio 0.6 --key-skew 1.2 --adversarial-ratio 0.15

# Step 1C: profile to see which backend is recommended
python hashmap_cli.py profile --csv runs/workloads/w_uniform.csv
python hashmap_cli.py profile --csv runs/workloads/w_skew_adv.csv --then get HOTKEY
```

### 2. Replay workloads with metrics + snapshots

```bash
# Step 2A: dry-run for validation first
python hashmap_cli.py run-csv --csv runs/workloads/w_uniform.csv --dry-run

# Step 2B: run with metrics streaming + JSON summary + snapshot
mkdir -p runs/metrics_uniform results/json snapshots
python hashmap_cli.py --config runs/demo_config.toml run-csv \
  --csv runs/workloads/w_uniform.csv \
  --metrics-port 9090 \
  --metrics-out-dir runs/metrics_uniform \
  --json-summary-out results/json/uniform_summary.json \
  --snapshot-out snapshots/uniform.pkl.gz --compress

# Step 2C: view metrics in Mission Control (new snapshot inspector + history controls)
python hashmap_cli.py mission-control

# Step 2D: confirm snapshot metadata from the CLI as well
python hashmap_cli.py inspect-snapshot --in snapshots/uniform.pkl.gz --limit 15 --key "'K1'"
```

### 3. Explore guardrails and migrations

```bash
# Step 3A: run a skewed workload to force Robin Hood migration + compaction
mkdir -p runs/metrics_skew
python hashmap_cli.py --mode adaptive run-csv \
  --csv runs/workloads/w_skew_adv.csv \
  --json-summary-out results/json/skew_summary.json \
  --metrics-out-dir runs/metrics_skew \
  --snapshot-out snapshots/skew.pkl.gz --compress

# Step 3B: inspect guardrail alerts in the TUI (optional)
python scripts/launch_tui.py --metrics-endpoint http://127.0.0.1:9090/api/metrics

# Step 3C: offline compact the Robin Hood snapshot then verify & repair
python hashmap_cli.py compact-snapshot --in snapshots/skew.pkl.gz --out snapshots/skew_compacted.pkl.gz --compress
python hashmap_cli.py verify-snapshot --in snapshots/skew_compacted.pkl.gz --repair --out snapshots/skew_repaired.pkl.gz --verbose
```

### 4. Compare configurations (A/B harness)

```bash
# Step 4A: create an alternate config (copy + tweak a field)
python hashmap_cli.py config-edit --infile runs/demo_config.toml --outfile runs/demo_config_candidate.toml --apply-preset default

# Step 4B: run paired benchmarks and collect comparison artifacts
python hashmap_cli.py ab-compare --csv runs/workloads/w_uniform.csv \
  --baseline-config runs/demo_config.toml \
  --candidate-config runs/demo_config_candidate.toml \
  --out-dir results/ab/uniform_demo

# Step 4C: surface throughput/latency deltas in the dashboard
python hashmap_cli.py serve --source results/ab/uniform_demo/artifacts/baseline/metrics/metrics.ndjson \
  --compare results/ab/uniform_demo/uniform_demo_baseline_vs_candidate.json
```

### 5. Batch suites & workload analytics

```bash
# Step 5A: run predefined suites (Markdown/HTML reports in results/)
python -m adhash.batch --spec docs/examples/batch_baseline.toml

# Step 5B: load the suite in Mission Control (Benchmark tab) to see log streaming and Workload DNA results
python hashmap_cli.py mission-control
```

By the end of this walkthrough you will have exercised config wizards, workload generation, live metrics (Mission Control + TUI), snapshot verification/repair, A/B comparisons, and batch reporting—the same flows covered in the automated audit.

---

## CLI Surface Overview

| Category | Commands | Notes |
| --- | --- | --- |
| Core ops | `put`, `get`, `del`, `items` | Work on any backend (`--mode adaptive`, `fast-lookup`, etc.). |
| Workloads | `generate-csv`, `profile`, `run-csv` | `run-csv` supports snapshots, live metrics, JSON summaries, dry-run validation, throttles. |
| Analytics | `workload-dna`, `ab-compare`, `inspect-snapshot` | Workload DNA reports skew/collision risk; `inspect-snapshot` surfaces versioned metadata and key lookups. |
| Config | `config-wizard`, `config-edit` | Schema-driven generator/editor with preset management. |
| Snapshots | `compact-snapshot`, `verify-snapshot` | Offline compaction/repair for RobinHood maps with checksum verification. |
| Observability | `serve`, `mission-control`, `scripts/launch_tui.py` | Dashboard server, desktop UI, and terminal UI. |

Run `python hashmap_cli.py -h` for the full command list with flags.

### JSON Envelopes & Exit Codes

- Add `--json` for machine-readable success payloads (`{"ok": true, "command": "run-csv", ...}`).
- Errors surface through standard envelopes (`BadInput`, `Invariant`, `Policy`, `IO`) with stable exit codes `{0,2,3,4,5}`.

---

## Snapshots & Configuration

- Snapshots use a versioned header + BLAKE2b checksum (`src/adhash/io/snapshot_header.py`). Untrusted payloads are rejected.
- Saved objects include Robin Hood/Chaining/Adaptive maps; `inspect-snapshot` and Mission Control’s inspector expose metadata, filtered previews, and direct key searches.
- Configs are dataclass-backed (`src/adhash/config.py`) with env overrides. `config-edit` and Mission Control’s editor share the same schema and validation logic.

Typical flows:

```bash
python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_heavy_adv.csv \
  --snapshot-out snapshots/adaptive.pkl.gz --compress

python hashmap_cli.py inspect-snapshot --in snapshots/adaptive.pkl.gz --key "'K1'" --limit 5

python hashmap_cli.py verify-snapshot --in snapshots/adaptive.pkl.gz --repair \
  --out snapshots/adaptive_repaired.pkl.gz --verbose
```

---

## Mission Control (PyQt6)

`python hashmap_cli.py mission-control`

Major panels:

- **Telemetry** – Throughput, load-factor, latency histogram, probe distribution, key heatmap, FFT analytics. The header reflects the exact tick/series you’re viewing. The “Keep history between runs” toggle preserves or resets charts between workloads.
- **Config Editor** – Schema-driven editor with preset refresh/save, fully synced with CLI tooling.
- **Snapshot Inspector** – Load `.pkl`/`.pkl.gz`, review header metadata, filter/search keys, export history, and monitor load-factor thresholds per snapshot.
- **Benchmark Suites** – Discover and run TOML specs using the batch runner, with live logs and workload DNA analysis.
- **Workload DNA** – Inspect CSV characteristics (ratios, entropy, hot keys) before execution.

Mission Control honours `ADHASH_TOKEN` for metrics authentication and gracefully handles headless environments (off-screen smoke tests live in `tests/test_mission_control_widgets_qt.py`).

---

## Textual TUI (Terminal)

`python scripts/launch_tui.py --metrics-endpoint http://127.0.0.1:9090/api/metrics`

- Displays backend status, operations, load-factor trends, guardrail alerts, and latency percentiles directly in the terminal.
- `r` to refresh, `q` to quit. Works with the same `/api/metrics` JSON endpoint as the dashboard.
- **IDE tip**: if you launch this from PyCharm/VSC, make sure the run configuration includes the `--metrics-endpoint` argument; otherwise the script will print the usage banner and exit.

---

## Batch Benchmark Runner

`python -m adhash.batch --spec docs/examples/batch_baseline.toml`

- Executes multi-run suites (profilers, `run-csv` jobs) and emits Markdown/HTML reports under `results/`.
- Mission Control’s Benchmark pane wraps the runner with a GUI for discovery, config, and log streaming.

See [`docs/batch_runner.md`](docs/batch_runner.md) for spec syntax and report details.

---

## Observability & Metrics API

`python hashmap_cli.py serve --port 9090 --source runs/metrics_demo/metrics.ndjson --follow`

- Serves `/api/metrics`, `/api/metrics/histogram/{latency,probe}`, `/api/metrics/heatmap`, `/api/metrics/history`, and `/api/events` in JSON.
- Optional Prometheus text output at `/metrics` (`docs/prometheus_grafana.md` has scrape configs, dashboards, alert examples).
- NDJSON artifacts (`--metrics-out-dir`, `--metrics-max-ticks`) retain historical ticks for replay, export, and offline analysis.
- Helper scripts:
  - `python scripts/query_metric_endpoint.py http://127.0.0.1:9090/api/metrics [dotted.jq.path]` – curl-style JSON fetcher (always pass the URL).
  - `python scripts/validate_metrics_ndjson.py runs/metrics_demo/metrics.ndjson` – schema validator (requires the NDJSON path).
  Configure run configurations in your IDE with these arguments; running “naked” will trigger the usage error banner you may have seen.

Set `ADHASH_TOKEN` to require `Authorization: Bearer …`. The browser dashboard accepts `?token=` for bootstrapping, and both Mission Control & TUI automatically include the header.

---

## Security Considerations

- Snapshots: versioned header + checksum, restricted unpickler. Treat third-party files as untrusted; the inspector surfaces checksum mismatches.
- Tokens: metrics dashboard enforces bearer tokens when `ADHASH_TOKEN` is set. No built-in TLS—front with your own reverse proxy for remote exposure.
- Guardrails: load-factor / probe / tombstone thresholds trigger alerts in logs, JSON, dashboards, TUI, and Mission Control banners.

---

## Validation

Run locally before every push/release:

```
make lint   # ruff
make type   # mypy
make test   # pytest (63 passed / 5 skipped as of Oct 05 2025)
```

Additional smoke:

- `make smoke` – generates a 2k-op workload and validates metrics output.
- `python scripts/validate_metrics_ndjson.py runs/metrics_demo/metrics.ndjson` – asserts schema compliance (`metrics.v1`).

Comprehensive command transcripts live in [`audit.md`](audit.md) and `reports/`. `reports/command_run_log.tsv` captures every automated/manual invocation with timestamps and status codes.

---

## Repository Map

```
├── hashmap_cli.py                # main CLI + data structures + metric server
├── src/adhash/                   # packaged modules (config, workloads, mission_control, tui, etc.)
├── scripts/                      # helper launchers (Mission Control, TUI, metrics query)
├── tests/                        # pytest + Qt/Textual smoke tests + CLI contract checks
├── docs/                         # configuration, metrics schema, batch runner, Prometheus/Grafana guides
├── data/                         # sample workloads/config presets referenced by docs
├── audit.md / systemwideaudit.md # manual verification transcripts (latest + historical)
├── upgrade.md                    # phased roadmap (Phase 0–4)
├── results/                      # JSON summaries, A/B comparisons, HTML reports
├── runs/                         # Generated artifacts during audits (metrics.ndjson, presets, suites)
├── snapshots/                    # Example snapshots used across walkthroughs/audits
├── reports/                      # Command logs, command inventory, full audit results
├── fixes.md                      # known issues & mitigations
└── README.md                     # this guide (kept in sync with audit results)
```

---

## Documentation & Audits

- [`audit.md`](audit.md) – authoritative verification log (12 sections + demo), refreshed Oct 2025.
- [`docs/config.md`](docs/config.md) – configuration schema and overrides.
- [`docs/metrics_schema.md`](docs/metrics_schema.md) – JSON shapes for ticks, histograms, heatmaps, events.
- [`docs/prometheus_grafana.md`](docs/prometheus_grafana.md) – integration guide for metrics exporters.
- [`docs/batch_runner.md`](docs/batch_runner.md) – benchmark specs & output format.
- [`docs/workload_schema.md`](docs/workload_schema.md) – CSV column definitions and validator behaviour.

---

## Contributing / Next Steps

1. Keep lint/type/test spotless; add new tests alongside features (UI widgets have Qt smoke tests under `tests/`).
2. Update `audit.md` and `reports/command_run_log.tsv` when adding major commands or artifacts.
3. Phase 3 work (deployment & integration) is tracked in [`upgrade.md`](upgrade.md): Docker packaging, release automation, Helm/Compose templates, etc.

Questions or patches? Open an issue or PR—just include the commands/tests you ran and highlight any schema or snapshot changes.
