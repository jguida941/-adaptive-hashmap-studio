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

## Production Gaps & Risks
- **Architecture**: 1,200+ line monolith; hard to extend, test, or import as a library. No packaging metadata or dependency pinning.
- **Testing & Quality Gates**: No automated unit/integration tests, fuzzing, or load validation; manual audit only. No static typing enforcement beyond annotations, no linting, no CI pipeline.
- **Configuration & Error Handling**: Config via env vars/ad-hoc arguments; no schema validation or hot reload. CSV parsing lacks schema validation and emits inconsistent exit codes/error envelopes.
- **Observability**: Metrics limited to a handful of counters/gauges; no histograms, latency breakdown per op, or persistent export. Logging handled via root logger without structured output or rotation.
- **Security**: Snapshots rely on pickle (unsafe for untrusted input). HTTP dashboard has no auth/TLS; metrics parser is regex-based. No resource quota protections.
- **Distribution & Ops**: No Dockerfile, pyproject, requirements, binaries, or release automation. No story for Prometheus/Grafana, upstream API integration, or packaging for pip/brew.
- **UX & Automation**: Dashboard is poll-only with minimal interactivity; no TUI for terminal use; no batch benchmark pipeline with reports.

## Recommendation
Yes—pursuing production hardening is worthwhile. The data-structure core and CLI workflows are already valuable; investing in modularization, automated validation, and richer observability will let the tool serve both educational and operational users. The roadmap below prioritizes foundational hygiene before UI polish to avoid locking in technical debt.

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
  - **Status:** Implemented (`src/adhash/config.py`, `--config` flag, TOML loader with env overrides; documented in docs/config.md).
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

### Phase 3 – Deployment & Integration
Goal: make the project consumable in production pipelines and external systems.
- Publish Dockerfile(s) for CPU-only and dev builds; include health checks and configurable ports.
- Provide Helm chart or Compose file for running long-lived services (metrics server + workload runner).
- Package library to PyPI (and optionally Homebrew) with semantic versioning and changelog automation (`towncrier` or similar).
- Integrate Prometheus exporters, Grafana dashboards, and alert rules; document setup.
- Add REST/GRPC API or Python bindings so other services can run workloads programmatically.
- Automate release builds with tagged CI workflows producing artifacts (Docker images, wheels, tarballs) and verifying checksums/signatures.
- Document operational runbooks (log locations, snapshot management, troubleshooting) and SLOs.

### Phase 4 – Advanced Analytics & Stretch Goals
Goal: leverage the richer platform for research and teaching value.
- Probe-path visualizer/animator (web or TUI) to demonstrate Robin Hood displacement and collisions.
- Adaptive policy experimentation: auto-tune thresholds via reinforcement learning or heuristic search; surface recommendations in the dashboard.
- Predictive analytics: train simple models (XGBoost, Prophet) to forecast when to migrate/compact; feed predictions into alerts.
- Cost modeling: track CPU cycles/op, memory footprint, GC stats; expose cost-per-op comparisons across backends.
- Streaming/remote workloads: accept live traffic via sockets/HTTP and feed metrics dashboards in real time.
- Multi-language support: share snapshot schema with C++/Rust implementations and build cross-language comparison harnesses.
- **Interactive Hash Map Explorer (PyQt6):** educational desktop tool that steps through operations, animates probe sequences, visualises buckets/slots, plays back small workloads, and highlights migrations/rehashes.
- **Workload DNA + Predictor:** integrate ML models that use the Workload DNA Analyzer to forecast backend performance, generate proactive recommendations, and annotate migrations/compactions with rich “Explain this event” diagnostics.
- **Statistical Insight Engine:** run statistical tests on latency histograms or throughput curves (p-value badges, regression trendlines) to quantify A/B differences inside Mission Control reports.
- **Jupyter Integration:** provide embeddable Qt widgets so Mission Control charts and Explorer views can be dropped into notebooks for reproducible research.

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
