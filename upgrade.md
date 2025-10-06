# Adaptive HashMap CLI – Production Upgrade Plan

This plan distills the current state of `hashmap_cli.py`, summarizes audit findings, and lays out a phased roadmap for turning the project into a maintainable, production-grade tool. Each phase builds on the previous one; you can stop after any phase if it already meets your goals.

## Current State Snapshot (Feb 2025)
- Single-file Python CLI (`hashmap_cli.py`) housing data structures, CLI plumbing, workload tooling, metrics buffer, and HTTP dashboard (Chart.js via CDN).
- Supports chaining, Robin Hood, and adaptive backends with snapshot save/load and verification helpers.
- CSV workload generator, profiler, and runner with latency reservoir sampling and NDJSON JSON summaries.
- Built-in `/metrics` endpoint and lightweight dashboard; metrics tracked: ops, puts, gets, dels, migrations, compactions, load factor, max group length, average probe estimate, backend label.
- Extensive manual audit documented in `audit.md`; no automated test suite, packaging metadata, or CI/CD automation in the repo.

## Core Strengths
- Clear separation of backends with adaptive migration logic + incremental batches.
- Rich CLI surface for profiling, running, verifying, compacting, and snapshotting workloads.
- Built-in observability primitives (metrics class, reservoir sampling, HTML dashboard) and hooks for callbacks during migrations/compactions.
- CSV-driven workflows and documented audit provide reproducible experimentation and reference artifacts.

## Progress Since Audit (Oct 2025)
- Repository now structured as an installable package under `src/adhash` with `pyproject.toml`, editable extras, and a matching `Makefile` / pre-commit workflow.
- Continuous Integration (`.github/workflows/ci.yml`) runs `ruff`, `mypy`, full `pytest`, and a smoke workload validator across Python 3.11/3.12; release automation is scaffolded via `release.yml`.
- Mission Control ships a dedicated Probe Visualizer tab and documentation (`docs/analysis/probe_visualizer.md`, README updates) describing JSON export + reload flows.
- Textual TUI integrates probe traces (`--probe-json`, `p` to reload) via the new `adhash.analysis.format_trace_lines`, keeping terminal diagnostics aligned with Mission Control.
- Snapshot loading hardened through `safe_pickle` allowlists; config now flows through typed TOML presets with validation helpers and tests.

## Production Gaps & Risks
- **Architecture**: 1,200+ line monolith; hard to extend, test, or import as a library. No packaging metadata or dependency pinning.
- **Testing & Quality Gates**: No automated unit/integration tests, fuzzing, or load validation; manual audit only. No static typing enforcement beyond annotations, no linting, no CI pipeline.
- **Configuration & Error Handling**: Config via env vars/ad-hoc arguments; no schema validation or hot reload. CSV parsing lacks schema validation and emits inconsistent exit codes/error envelopes.
- **Observability**: Metrics limited to a handful of counters/gauges; no histograms, latency breakdown per op, or persistent export. Logging handled via root logger without structured output or rotation.
- **Security**: Snapshots previously relied on pickle (unsafe for untrusted input). HTTP dashboard had no auth/TLS; metrics parser is regex-based. No resource quota protections.
  - **Status:** Snapshot loading now flows through a restricted allowlist (`safe_pickle`), and dashboard clients enforce token auth end-to-end. TLS/quota enforcement remains on the roadmap.
- **Distribution & Ops**: No Dockerfile, pyproject, requirements, binaries, or release automation. No story for Prometheus/Grafana, upstream API integration, or packaging for pip/brew.
- **UX & Automation**: Dashboard is poll-only with minimal interactivity; no TUI for terminal use; no batch benchmark pipeline with reports.

## Recommendation
Yes—pursuing production hardening is worthwhile. The data-structure core and CLI workflows are already valuable; investing in modularization, automated validation, and richer observability will let the tool serve both educational and operational users. The roadmap below prioritizes foundational hygiene before UI polish to avoid locking in technical debt.

- [x] Harden CLI QA (Oct 2025): added probe-visualize error-path contracts and NDJSON validator regression tests (`tests/test_cli_probe_command.py`, `tests/test_validate_metrics_ndjson.py`).
- [x] Enable automated coverage reporting in CI (Oct 2025): GitHub Actions now runs `coverage run -m pytest` with a fail-under baseline of 50 % (planned ratchet toward 80 %).
- [x] Stabilize distribution artifacts by finalizing `LICENSE`/`NOTICE`, generating an SBOM during `make release`, and documenting signing/verification steps alongside the new release workflow. *(Oct 2025: `LICENSE`/`NOTICE` committed, `scripts/build_release_artifacts.py` + `make release`, runbook updated with verification steps.)*
- [x] Produce operational runbooks (`docs/ops/`) covering deployment, token/TLS configuration, and smoke procedures for Docker / Mission Control to support on-call handover. *(Oct 2025: `docs/ops/runbook.md` added and linked from README.)*
- [x] Extend Mission Control/TUI parity tests (Textual harness, Qt widget snapshots) so probe visualizer regressions fail fast. *(Oct 2025: new coverage in `tests/test_mission_control_widgets_qt.py` and `tests/test_tui_probe.py`.)*
- [x] Finish authoring `upgrade.md` Phase summaries with acceptance criteria + current status flags so stakeholders can track momentum without diffing history. *(Oct 2025 refresh captured for all phases.)*

## Phased Roadmap

### Phase 0 – Strategy & Baseline Hardening *(in progress — core scaffolding complete)*
Goal: carve the monolith into a maintainable project and establish quality gates.
- Define supported Python versions, performance targets, and release cadence; document non-goals (e.g., no distributed mode yet).
- Split code into a package structure (`src/adhash/…`) with modules for backends, adaptive controller, workloads, metrics, CLI entrypoints, and HTTP server. Maintain CLI via `python -m adhash.cli` or console script.
- Introduce `pyproject.toml`, `requirements.txt`, and environment files; pin third-party dependencies (Chart.js is CDN-based—decide on vendoring).
- Add lint/type/test tooling: `ruff` or `flake8`, `mypy`, `pytest`, optional `hypothesis` for property tests, `pre-commit` hooks.
- Write unit tests covering put/get/delete, migration triggers, snapshot round-trips, CSV parsing edge cases. Add quick integration tests for `run-csv` with small workloads.
- Set up GitHub Actions (or preferred CI) to run lint, type-check, tests, and a smoke `run-csv` replay per PR.
- Establish structured logging (JSON formatter + rotating file handler) and consistent error envelopes/exit codes for CLI failures.
- Replace ad-hoc env parsing with typed config objects (e.g., `pydantic` or dataclasses + `tomllib`). Provide a single canonical config file format (TOML/YAML) and document overrides.
  - **Status:** Implemented (`src/adhash/config.py`, `--config` flag, TOML loader with env overrides; documented in docs/config.md). Preset files now validate through `validate_preset_file()` and typed schema helpers in `src/adhash/config_models.py`, with regression coverage in `tests/test_config_toolkit_schema.py`.
- Externalize dashboard assets so HTML/CSS/JS are versioned under `src/adhash/metrics/static/` and loaded via `importlib.resources`, keeping the Python server lean. **Status:** Implemented alongside asset integrity tests.
- Land the **Phase-0 accuracy kit** so contracts are enforced from day one:
  - Add `src/adhash/contracts/error.py` (error envelope helpers, `Exit` codes, `guard_cli` decorator) and refactor CLI entrypoints to raise typed exceptions and return `int(Exit.OK)`; update integration tests accordingly.
  - Introduce `src/adhash/contracts/metrics_schema.json` and `scripts/validate_metrics_ndjson.py`; stamp `"schema": "metrics.v1"` onto every tick and wire the validator into CI.
  - Add `src/adhash/io/snapshot_header.py` with versioned, checksummed snapshot helpers; replace direct pickle/gzip calls in the CLI and write unit tests for round-trip and tamper detection.
  - Create supporting tests (`tests/test_cli_contracts.py`, `tests/test_metrics_schema.py`, `tests/test_snapshot_header.py`) plus golden fixtures as needed; ensure `pytest` runs them in CI and they’re referenced in the Definition-of-Ready/PR template.
  - Update `pyproject.toml` dev extras, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, and `.github/PULL_REQUEST_TEMPLATE.md` to include the guardrails; commit template + instructions to CONTRIBUTING.
  - Add documentation stubs (`docs/metrics_schema.md`, `docs/error_envelope.md`, `docs/snapshot_format.md`, `docs/workload_schema.md`, `docs/config.md`, `SECURITY.md`) capturing the frozen contracts; link them from README/CONTRIBUTING so every change references written specs.
  - Add a `Makefile` (lint/type/test/cov/smoke/validate/precommit) and a concise `CONTRIBUTING.md` that references the Definition-of-Ready, PR checklist, and required commands; ensure CI runs `make smoke` (or equivalent) to exercise metrics validation automatically.
  - Extend `.github/PULL_REQUEST_TEMPLATE.md` with author/reviewer checklists, including contract-change boxes and required logs (pytest summary, schema validator output, snapshot tests).
  - **Status:** Implemented. Structured logging now supports JSON + rotating file handler via CLI flags; metrics validator enforces monotonic percentiles; smoke target auto-creates `runs/`; `py.typed` added and packaging aligned to Python 3.11+.

### Phase 1 – Reliability, Observability & Safety
Goal: deepen runtime visibility, harden I/O paths, and protect data integrity.
- Expand metrics: load factor per backend, probe-length histogram, per-op latency (p50/p90/p99) by operation, tombstone ratio, migration/compaction timeline. Serve JSON APIs alongside Prometheus text to feed richer UIs.  - **Status:** Completed — ticks now carry per-op percentiles, probe histograms, migration/compaction events; `/api/metrics` serves JSON and metrics.ndjson retention is tunable.
- Harden CSV ingestion: schema validation, clear errors, optional dry-run mode, and guardrails for huge files (size/row limits).  - **Status:** Completed — CSV validator enforces header/row diagnostics, `--dry-run`/`--csv-max-*` flags add guardrails, and error envelopes point back to docs.
- Introduce snapshot format versioning and consider safer serialization (capnproto/flatbuffers/custom) or at minimum document security risks; add signature or checksum validation.  - **Status:** Completed — versioned header + BLAKE2b checksum shipped (`src/adhash/io/snapshot_header.py`), docs/spec/tests added.
- Rework CLI error handling: consistent return codes, summary of failures, optional `--json` output to integrate with scripts.  - **Status:** Completed — success-path envelopes now ship behind `--json`, docs updated, and contract tests cover the new output.
- Add watchdog alerts: threshold-based notifications (CLI log + dashboard highlight) when load factor/probe length/tombstone ratio crosses configured limits.  - **Status:** Completed — guardrail config + log/banner alerts shipped.
- Integrate Prometheus exporters, Grafana dashboards, and alert rules; document setup.  - **Status:** Completed — see `docs/prometheus_grafana.md` (scrape config, alert rules) and `docs/grafana_dashboard.json` for an importable overview dashboard.
- Instrument performance regression tests; capture baseline throughput/latency in CI (small workloads) and compare with tolerances.  - **Status:** Completed — `tests/test_perf_smoke.py` executes a 200-op replay, asserts ops/s > 0, and validates metrics.ndjson against `metrics.v1`.
  - Stretch targets: embed 3D visualisations (e.g., load-factor surfaces), integrate with notebooks via Qt widgets, allow local/offline use without the HTTP server.


### Phase 2 – User Interfaces & Workflow Enhancements
Goal: deliver polished interactive experiences for both terminal and browser users.
- Replace static Chart.js dashboard with interactive charts (Plotly, ECharts, or D3) featuring zoom/pan, tooltips, multi-series overlays, theming, and adjustable polling intervals.
- Expose new dashboard panels: latency histograms, probe-length bar charts, key-distribution heatmaps, migration/compaction timeline, alert banners.
- Publish REST endpoints for histogram/heatmap data to avoid parsing Prometheus text.
- Build a TUI (`textual`, `urwid`, or `rich`) showing real-time metrics, alerts, and backend status for environments without browsers.
- Add batch benchmark runner accepting YAML/TOML specs; execute multiple workloads/backends, aggregate stats, and emit Markdown/HTML/PDF reports with charts.
- Offer configuration UI (CLI wizard or web form) to adjust adaptive thresholds and workload definitions without editing files.
- Provide `--serve` / sticky server mode to decouple metrics dashboard lifecycle from CSV runs, and optionally persistence/replay of metric history.
- **Mission Control (PyQt6):** desktop app to configure runs, launch `run-csv`, and visualise `/api/metrics` in real time (pyqtgraph plots, latency histograms, probe-length distribution, migration/compaction timeline) with a live log viewer.
- **A/B Live Comparison:** run two configurations side-by-side with synchronized charts, automatic config diffs, and statistical significance badges for latency/throughput comparisons.
- **Benchmark Suite Manager:** GUI for defining benchmark suites (YAML/TOML), executing batch runs, browsing historical results, and generating comparison reports/plots.
- **Workload DNA Analyzer:** pre-run inspection of CSV workloads (ratios, skew, collision potential) feeding Mission Control and predictors. ✅ `hashmap_cli.py workload-dna` plus Mission Control's **Workload DNA** panel landed Oct 5 2025.
- **Visual Config Editor & Snapshot Inspector:** schema-driven editor for `config.toml` plus a snapshot browser for `.pkl.gz` files (metadata, key search/filter).
- Build a rich PyQt6 analytics dashboard (desktop app) replicating and exceeding browser features: multi-chart layout, interactive drill-down, historical replay, advanced filtering, scientific plotting (FFT on latency, scatter/correlation plots), configurable alerts, notebook export.
  - Stretch targets: embed 3D visualisations (e.g., load-factor surfaces), integrate with notebooks via Qt widgets, allow local/offline use without the HTTP server.

#### Phase 2 – Immediate Next Actions (Oct 3, 2025)
- Harden the metrics REST surface: finish `histogram`, `heatmap`, and latency percentile endpoints in `src/adhash/metrics/server.py`, add schema fixtures, and extend `tests/test_metrics_endpoints.py` to cover new payloads.
- Upgrade the dashboard frontend (`adhash/dashboard/`) to consume the new endpoints: add latency histogram + probe-length charts, timeline annotations for migrations/compactions, and wire in adjustable polling intervals. ✅ Timeline markers + polling selector wired Oct 3 2025; remaining work: expose migration timeline in UI log.
- Expand the batch runner into a suite manager: ingest multi-run specs, capture comparative summaries, and emit Markdown/HTML bundles with chart embeds for Phase 2 demos. ✅ Comparative summary tables + inline HTML bars landed Oct 3 2025; Mission Control now ships a **Benchmark Suites** tab that loads specs and launches runs via the batch runner (Oct 5 2025).
- Ship a config editor toolkit: reuse the wizard schema to drive an interactive CLI/editor module plus Mission Control panel for editing `config.toml` and storing presets. ✅ CLI + Mission Control editors landed Oct 4 2025 (preset manager + shared validation).
- Prototype the A/B comparison harness: orchestrate paired `run-csv` executions, align metrics streams, calculate significance (p99 latency ± throughput deltas), and surface results in both the dashboard and Mission Control. ✅ `ab-compare` CLI + `serve --compare` summary landed Oct 4 2025 (ops/latency deltas + timeline export).
- Stickier serve mode follow-ups – Now that markers/log persistence is in place, add any remaining UX polish (e.g., richer event details or timeline export). ✅ Timeline CSV export + dashboard comparison strip landed Oct 4 2025.
- Convert the PyQt6 Mission Control spike into a modular app: factor controllers/views under `src/adhash/mission_control/`, add smoke tests that use the off-screen auto-quit hook, and document headless validation steps in `docs/command_audit.md`. ✅ Builders + controller wiring landed Oct 4 2025; headless Qt test exercises widget/controller assemblers.

➡️ **Current focus moves to Phase 3 – Deployment & Integration (Docker packaging, CI, Helm charts). Pending bullets below remain untouched until we finish those deliverables.**


### Phase 3 – Deployment & Integration
Goal: make the project consumable in production pipelines and external systems.
> **Status (Oct 2025):** Docker packaging (production + dev images), compose stack, and a tag-driven release workflow are complete. Remaining bullets focus on ecosystem integrations and distribution.
- [x] Publish Dockerfile(s) for CPU-only and dev builds; include health checks and configurable ports.
- [x] Provide Helm chart or Compose file for running long-lived services (metrics server + workload runner).
- [x] Package library to PyPI (and optionally Homebrew) with semantic versioning and changelog automation (`towncrier` or similar). *(Release workflow now uploads to TestPyPI/PyPI when API tokens are provided; runbook documents the manual Homebrew bump workflow while we wire automation.)*
- [x] Integrate Prometheus exporters, Grafana dashboards, and alert rules; document setup. *(Prometheus exporter exercised in `tests/test_metrics_endpoints.py`; setup captured in `docs/prometheus_grafana.md` with dashboard JSON and sample alerts.)*
- [ ] Add REST/GRPC API or Python bindings so other services can run workloads programmatically. *(Architectural plan captured in `docs/control_surface.md`; waiting on implementation milestone and security review.)*
- [x] Automate release builds with tagged CI workflows producing artifacts (Docker images, wheels, tarballs) and verifying checksums/signatures.
- [x] Document operational runbooks (log locations, snapshot management, troubleshooting) and SLOs. *(Oct 2025: `docs/ops/runbook.md` covers smoke checks, logs, incident response, release verification.)*

### Phase 4 – Advanced Analytics & Stretch Goals
Goal: leverage the richer platform for research and teaching value.
- [x] Probe-path visualizer/animator (CLI foundation in place; feeds Mission Control instrumentation).
- Adaptive policy experimentation: auto-tune thresholds via reinforcement learning or heuristic search; surface recommendations in the dashboard.
- Predictive analytics: train simple models (XGBoost, Prophet) to forecast when to migrate/compact; feed predictions into alerts.
- Cost modeling: track CPU cycles/op, memory footprint, GC stats; expose cost-per-op comparisons across backends.
- Streaming/remote workloads: accept live traffic via sockets/HTTP and feed metrics dashboards in real time.
- Multi-language support: share snapshot schema with C++/Rust implementations and build cross-language comparison harnesses.
- **Interactive Hash Map Explorer (PyQt6):** educational desktop tool that steps through operations, animates probe sequences, visualises buckets/slots, plays back small workloads, and highlights migrations/rehashes.
- **Workload DNA + Predictor:** integrate ML models that use the Workload DNA Analyzer to forecast backend performance, generate proactive recommendations, and annotate migrations/compactions with rich “Explain this event” diagnostics.
- **Statistical Insight Engine:** run statistical tests on latency histograms or throughput curves (p-value badges, regression trendlines) to quantify A/B differences inside Mission Control reports.
- **Jupyter Integration:** provide embeddable Qt widgets so Mission Control charts and Explorer views can be dropped into notebooks for reproducible research.

#### Phase 4 Milestones (Draft)

**M4.1 – Interactive Hash Map Explorer Alpha (3 sprints)**
- **Scope**: Standalone PyQt6 window embedding the existing Mission Control chart components with a deterministic playback engine that can step through insert/get/delete operations. Include bucket visualisation, probe animation, and editable workloads under 1k ops.
- **Dependencies**: Finalise REST control surface (Phase 3), refresh snapshot schema docs, reuse `adhash.analysis.probe` plumbing.
- **Deliverables**:
  - New package `adhash.explorer` with Qt widgets, command palette, and JSON import/export.
  - CLI entry point `hashmap-cli explorer --snapshot ...` launching the explorer with playback controls.
  - Tutorial in `docs/explorer/quickstart.md` plus recorded demo.
- **Acceptance**: QE walkthrough exercises three workloads (uniform, skew, adversarial), confirms step controls, verifies probe overlays, and ensures state rewind works without crashes.

**M4.2 – Adaptive Policy Lab (2 sprints)**
- **Scope**: Experimental orchestrator that runs policy variants (thresholds, reinforcement-learning agents) against canonical workloads and surfaces recommendations via Mission Control + reports.
- **Dependencies**: Control surface job API (Phase 3), batch runner HTML report pipeline, metrics schema v1.
- **Deliverables**:
  - `adhash.lab` module housing policy definitions, evaluation harness, and summary exporters.
  - CLI command `hashmap-cli policy-lab --suite docs/examples/policy_lab.toml` producing Markdown/HTML comparisons.
  - Mission Control pane that loads lab outputs and highlights recommended policy deltas.
- **Acceptance**: Automated test suite runs two baseline policies vs. a candidate, asserts diff calculations, and generates artifacts validated by `scripts/validate_metrics_ndjson.py`. UX review signs off on dashboard integration and documentation in `docs/policy_lab.md`.

**Backlog – M4.3+**
- Predictive analytics, statistical insight engine, Jupyter widgets, and cross-language support remain scoped for later planning cycles once M4.1/M4.2 land.

## Cross-Cutting Considerations
- **Documentation**: Maintain a revamped README, API docs (Sphinx/MkDocs), architecture diagrams, and “how to reproduce audit” guides. Version them alongside releases.
- **Data Governance**: Clarify retention/deletion policies for snapshots and metric logs. Provide scrubbers for sensitive data in workloads.
- **Performance Targets**: Establish baseline throughput/latency targets per workload class; automate regression detection.
- **Security & Access**: Consider TLS, auth tokens for the HTTP dashboard, and sandboxing when running untrusted workloads.
- **Open Questions**: (a) Who operates long-running instances? (b) Are workloads ever multi-tenant? (c) Do we need SLA-backed alerting integrations (PagerDuty, Slack)? Document assumptions before Phase 2.

## Next Actions
1. Review and approve the phased strategy (focus first on Phase 0 scope and resource allocation).
2. Create issues/epics per phase, populate with tasks from the bullet points above, and assign owners.
3. Start Phase 0 with repo restructuring, tooling, and first wave of unit tests; update `audit.md` to link to automated equivalents as they land.

Once Phase 0 ships you’ll have a foundation to iterate safely; subsequent phases can then concentrate on UX polish and advanced analytics without risking core stability.

Throughout execution, test after each feature lands (unit + CLI contract + metrics schema) and append the outcomes to `audit.md` so manual and automated evidence stay in lockstep.

## Execution Guardrails & Standards

Lock these constraints in before work begins so every phase has clear pass/fail criteria and avoids mid-stream debates.

- **Definition of Done per Phase**
  - Phase 0: package layout under `src/…`, `pyproject.toml` + lock files, CI running lint/mypy/tests, ≥80 % type coverage, standardized exit-code policy, JSON error envelope live, unit + integration smoke tests passing.
  - Phase 1: metrics schema v1 documented and stable, NDJSON persistence via `--metrics-out-dir`, Prometheus exporter parity, CSV schema validation with row/column reporting, snapshot headers carry version + checksum.
  - Phase 2: TUI renders ops/load-factor/p50/p99, dashboard shows migration markers + probe histogram, sticky `--serve` mode operational, batch runner emits Markdown/HTML report artifact.
  - Phase 3: Docker images published with SBOM + provenance labels, signed wheels/sdist, Grafana dashboard JSON checked in, release pipeline tags and generates changelog automatically.

- **Stable Contracts to Freeze Now**
  - Error envelope: `{"error": "<Code>", "detail": "...", "hint": "..."}` with exit codes `{0 OK, 2 BadInput, 3 Invariant, 4 Policy, 5 IO}`; enforce across CLI paths.
  - Metrics tick schema v1 (add `"schema": "metrics.v1"` if desired) as:
    ```json
    {
      "t": 0.0,
      "backend": "robinhood",
      "ops": 0,
      "puts": 0,
      "gets": 0,
      "dels": 0,
      "load_factor": 0.0,
      "probe_hist": [[1, 0]],
      "latency_ns": {"p50": 0, "p90": 0, "p99": 0},
      "events": [{"type": "switch", "from": "chaining", "to": "robinhood", "reason": "LF>0.8", "t": 0.0}]
    }
    ```
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
    ```yaml
    name: ci
    on: [push, pull_request]
    jobs:
      build:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: '3.12'
          - run: pip install -U pip
          - run: pip install -e .[dev]
          - run: ruff check .
          - run: mypy .
          - run: pytest -q
    ```
  - Extend with matrix/bench jobs as budgets allow.

- **Observability Parity Checklist**
  - Ensure a single metrics producer feeds three consumers: NDJSON writer (`--metrics-out-dir`), Prometheus exporter, and dashboard polling JSON endpoints; keep schemas consistent.

- **Documentation Set**
  - Maintain `upgrade.md`, `docs/workload_schema.md`, `docs/metrics_schema.md`, `docs/snapshot_format.md`, and an operational runbook (ports, logs, rotation, recovery procedures).

- **Supply Chain & Release Management**
  - Pin dependencies, produce SBOMs, sign release artifacts, annotate Docker images with repo/VCS labels, and automate changelog generation (e.g., `towncrier`).

These guardrails make the roadmap execution-ready: every phase has observable success criteria, contracts stay stable, and operational risks are addressed early.

## Testing Strategy by Phase

- **Phase 0**
  - High-confidence unit tests for core data-structure operations (put/get/delete), adaptive migration triggers, snapshot round-trip, CSV parsing (happy path + malformed cases).
  - Integration smoke: end-to-end `run-csv` with mini workload, verify JSON summary + metrics tick schema.
  - Static coverage goals: ≥80 % type-hinted code exercised; add coverage reporting to CI for visibility.

- **Phase 1**
  - Extend unit tests to new metrics collectors, NDJSON writer, Prometheus exporter, CSV validator, and snapshot header parsing.
  - Regression tests for error envelope and exit codes (parameterized CLI invocations returning expected JSON + status).
  - Property/fuzz tests for CSV ingestion and metrics histogram bounds.

- **Phase 2**
  - UI harness tests: snapshot-based tests for TUI rendering (using `textual` test utilities) and REST endpoints powering dashboard charts.
  - Batch runner integration tests producing deterministic Markdown/HTML artifacts (golden files).
  - Contract tests ensuring dashboard and NDJSON consumers stay schema-compatible.

- **Phase 3**
  - Container smoke tests (Docker build + `hashmap-cli --help`, sample run inside container).
  - Release pipeline tests verifying signed artifacts and changelog generation.
  - Optional lightweight performance regression test (e.g., 10k-op workload) to run in CI matrix.

- **Phase 4**
  - Visualization correctness checks (probe animator frames), ML pipeline unit tests with synthetic traces, cross-language snapshot compatibility tests.

Every new feature merges with accompanying tests; failures block promotion to subsequent phases.

## Accuracy & Automation Framework

- **Definition of Ready template** (attach to issues/PR tickets): captures goal, impacted contracts (metrics.v1, error envelope, snapshot format), acceptance criteria (unit + CLI contract tests, docs updates, perf budget), constraints (deps, forbidding sleeps/network), and standard mini workload test data. No task starts without a completed DoR.
- **Pull Request template** enforcing self-verification: summary, impacted contracts checklist, test evidence (pytest, CLI contract tests, NDJSON schema validator, snapshot round-trip), rollback plan, and logs/screens. Make it mandatory in repo settings.
- **CLI contract tests** (`tests/test_cli_contracts.py`): subprocess harness validating exit codes/error JSON for representative failure scenarios (missing CSV, bad header, etc.). Wired into pytest via standard CI.
- **Metrics schema validator** (`scripts/validate_metrics_ndjson.py`): asserts each NDJSON line carries `schema: "metrics.v1"` and required fields; run automatically in CI whenever artifacts are produced.
- **CSV fuzz/property tests** (`tests/test_csv_fuzz.py` with Hypothesis): ensure parser robustness across randomized inputs and malformed rows without crashes.
- **Golden contract fixtures** (`tests/golden/metrics_small.ndjson`, dashboard API responses): detect accidental schema drift while allowing value ranges.
- **Snapshot safety tests**: enforce checksum/version header, wrong-backend/error-path coverage, and tamper detection.
- **CI pipeline gates**: lint (`ruff`), type-check (`mypy`), pytest (unit + property + CLI contract), schema validator, optional `bandit`. Enforce coverage thresholds (Phase 0 ≥ 75 %, ratchet upward each phase).
- **Pre-commit config**: `ruff --fix`, `mypy`, `black` to catch format/type issues before CI; document installation in CONTRIBUTING.
- **AI delivery protocol**: every patch must include diffs or file replacements, explain preserved invariants/contracts, list added/updated tests, note doc changes, and paste self-run command outputs (pytest, schema validator). Make this part of the PR template / review checklist
