# CI/CD & Mutation Automation Guide

This repository ships with a set of GitHub Actions workflows plus matching
local tooling to keep quality gates tight without slowing iteration. Use this
guide as a quick reference when cloning the setup in other projects.

## Workflows at a Glance

### `.github/workflows/ci.yml`
- **Triggers:** `push` to `main`, all pull requests.
- **Matrix:** Python 3.11 and 3.12 on Ubuntu.
- **Pre-gates:** `ruff` lint, `mypy`, full pytest suite under coverage
  (with Qt/Xvfb deps preinstalled).
- **Outputs:** `coverage.xml` uploaded to Codecov, plus a smoke run via
  `make smoke` to validate CLI + schema tooling.
- **Extras:** Concurrency guard cancels superseded runs; caches for pip,
  Hypothesis, and pytest state speed up reruns; a slowest-tests table is written
  both to an artifact (`pytest-slowest.md`) and the job summary for quick triage.

### `.github/workflows/mutmut.yml`
- **Triggers:** same as CI.
- **Steps:** installs deps, runs `mutmut run`, then invokes
  `tools/mutants_report.sh` to generate reports.
- **Artifacts:** uploads the entire `.mutmut-ci/` directory along with
  `mutmut_results.txt` (raw summary) and `survivors_summary.md`.
- **Job summary:** appends a concise scoreboard (“🎉 killed …”) to
  `$GITHUB_STEP_SUMMARY` so reviewers see mutation status without opening logs.
- **Fail behaviour:** currently report-only. Future enhancement can gate on
  survivor deltas per touched file.
- **Extras:** Concurrency guard cancels superseded runs; caches for pip,
  `.mutmut-cache/`, and `.hypothesis/` keep mutation runs fast.

## Beginner Quickstart

1. Clone the repo and run `make lint type test` to match the CI pre-gates.
2. Run `make mutants-report-local` to see the latest mutation survivors from
   your machine and inspect the generated TODO stubs.
3. When editing tests involving Hypothesis, import
   `tests.util.hypothesis_profiles` (already done in `tests/conftest.py`) so the
   shared `dev`/`ci` profiles apply automatically. Locally, the lightweight
   `dev` profile runs by default; CI sets `HYPOTHESIS_PROFILE=ci` for more
   thorough, deterministic runs.
4. Before pushing, skim `pytest-slowest.md` (created by CI) and the mutation
   scoreboard in the PR summary to understand current hotspots.
5. Refer to `docs/testing/flaky_policy.md` any time you need to quarantine a
   flaky test.
6. Use `docs/testing/mutation_automation.md` when you want Codex or scripts to
   auto-iterate on survivors until targets are met.

### `.github/workflows/release.yml`
- Builds and publishes tagged releases. Run `make release` locally first to
  ensure artifacts match expectations.

## Local Helper Commands

| Command | Purpose |
| --- | --- |
| `make mutants-report` | Downloads the latest Actions artifact (requires `gh auth login`), rebuilds Markdown + JSON survivor reports, and drops TODO test stubs. |
| `make mutants-report-local` | Skips GitHub interaction; summarises the local `mutmut results` output and still creates TODO stubs. |
| `make type`, `make lint`, `make test` | Mirror the CI pre-gates. Running them locally keeps pipelines green on first try. |
| `tools/mutants_orchestrator.sh` | Automated mutation loop: run mutmut, regenerate reports, scaffold TODOs, and repeat until survivor targets are met (supports dry-run). |

### Test/Lint Suite Cheat Sheet

| Command | CI Step | What it checks | When to run locally |
| --- | --- | --- | --- |
| `ruff check .` (`make lint`) | “Lint” in `ci.yml` | Style + common bug patterns (unused imports, shadowed vars, etc.) | Before opening a PR; fixes most static issues quickly. |
| `mypy .` (`make type`) | “Type check” in `ci.yml` | Static type correctness across `src/` and `tests/`; uses local stubs under `stubs/` | After touching interfaces or adding new modules. |
| `pytest -q` (`make test`) | “Unit tests & coverage” in `ci.yml` | Entire test suite under `tests/`; produces coverage data | Any behavioural change; smoke it before pushing. |
| `coverage run -m pytest -q` (`make cov`) | same step | Records per-line coverage for reporting/Codecov upload | When validating coverage deltas locally. |
| `make smoke` | “Smoke workload & schema validation” | End-to-end CLI workflow: generate workload, run adaptive mode, validate metrics schema | Before release or when touching CLI/service wiring. |
| `mutmut run` (driven by workflow + `tools/mutants_report.sh`) | `mutmut.yml` | Mutation testing across `src/adhash/core, src/adhash/cli`; reports survivors, drops TODO stubs | After adding tests meant to kill specific mutants; can restrict scope with `MUTATE_PATHS=`. |
| Property-based tests (`tests/test_maps_properties.py`, etc.) | part of pytest run | Exercises invariants with Hypothesis; emits failing examples to artifacts when assertions break | Re-run if you touch algorithms (`src/adhash/core/maps.py`) or fixtures used in property tests. |

The mutation helper script lives at `tools/mutants_report.sh`. Key env toggles:

| Variable | Default | Description |
| --- | --- | --- |
| `WORKFLOW` | `mutation-tests.yml` | Actions workflow to fetch artifacts from. |
| `ART_NAME` | `mutmut-results` | Artifact name to download. |
| `TOPN` | `25` | Number of survivor diffs to embed in the Markdown report. |
| `REPORT_DEST` | `file` | Choose `file`, `stdout`, `issue`, `pr`, or `none`. |
| `MUTANTS_LOCAL_ONLY` | `0` | Set `1` to skip artifact fetch entirely. |
| `SKIP_MUTMUT_INSTALL` | `0` | Set `1` if `mutmut`/`pytest` already installed. |

Artifacts written by the script:
- `.mutmut-ci/survivors_report.md` – human-readable, limited to top `TOPN`.
- `.mutmut-ci/survivors_report.json` – schema versioned (`schema_version=1`)
  with per-mutant metadata (id, file, line, diff).
- `.mutmut-ci/github_step_summary.md` – short snippet appended to the Actions
  job summary.
- `tests/mutation_todos/…` – placeholder pytest modules, one per affected file,
  marked with `@pytest.mark.mutation_todo` (replace with real assertions to
  kill mutants).
- `pytest-slowest.md` – top 10 slowest pytest calls from the latest CI run.

## Suggested Triage Loop

1. Let Actions finish the mutation workflow (you’ll see the scoreboard in the
   PR summary).
2. Run `make mutants-report` locally to pull the artifact and generate stubs.
3. For each survivor diff, craft targeted tests to kill the mutant and replace
   the placeholder in `tests/mutation_todos/`.
4. Rerun `mutmut run` (or push to trigger CI) and repeat until survivor counts
   trend down.

## Rollout Playbook for New Projects

1. **Pre-gates first:** add `ruff`, `mypy`, and `pytest -q` steps. Fail fast.
2. **Mutation reporting:** wire in `mutmut run` + `tools/mutants_report.sh`
   (report-only). Upload Markdown + JSON artifacts.
3. **Deltas:** once stable, enforce “no new survivors in touched files” and
   “no coverage drop >1% in touched modules”.
4. **Noise control:** use `# pragma: no mutate` + allowlists for true
   equivalents, review additions carefully.
5. **Observability:** keep `$GITHUB_STEP_SUMMARY` clean—one dashboard line per
   workflow; detailed data in artifacts.

## Additional Tips

- Cache `.mutmut-cache/` and `.hypothesis/` between runs to shrink cycle time.
- Override mutation scope with `MUTATE_PATHS=src/adhash/core mutmut run` while
  iterating; restore the wider scope before merging.
- Document per-module survivor SLOs (e.g., “0 new survivors in `core/`”) to
  set expectations for contributors.
- Use fine-scoped GitHub tokens (or Actions workflows) when auto-posting
  issues/comments to stay within least-privilege boundaries.
- When running multiple mutation jobs in parallel, follow the worktree playbook
  in `docs/ops/mutation_worktrees.md` to isolate caches and coordinate Codex
  sessions.

## Keeping Workflows Quiet

### Workflow Hygiene & Stability
- **Quarantine flaky tests:** tag with `@pytest.mark.flaky` and run them in a
  non-blocking job until repaired so the primary CI lane stays green.
- **Determinism by default:** set `PYTHONHASHSEED=0`, enable `pytest-randomly`
  (log the seed), and adopt a Hypothesis `ci` profile (`deadline=None`, tuned
  `max_examples`, `print_blob=True`).
- **Timeout discipline:** configure `pytest-timeout` with sensible budgets and
  bump limits for mutation jobs that explore deeper paths.
- **Cancel superseded runs:** add GitHub Actions concurrency guards to stop
  outdated jobs automatically:
  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: true
  ```

### Speed & Signal
- Cache `.mutmut-cache/`, `.hypothesis/`, `.pytest_cache/`, and wheel dirs with
  keys that include lockfile hashes.
- Shard heavy suites: use `pytest-xdist --dist=worksteal`, split mutation runs
  by package (`core`, `cli`, …) to tame runtimes.
- Document “fast loop” targets such as `make quick-test`, `make mutants-core`,
  and `make smoke` so contributors can run high-signal subsets before CI.

### Mutation-Specific Quieting
- Maintain an allowlist policy: every `# pragma: no mutate` or survivor
  allowlist entry should include PR rationale and codeowner approval.
- Keep `use_coverage = 1` (already set) and ensure coverage pre-gates execute
  before mutmut so cold code stays untouched.
- Add a per-file survivor delta gate: warn first when touched files gain
  survivors, then enforce once the backlog shrinks.

### Artifacts & Telemetry
- Limit retention (e.g., 7–14 days) and compress large artifacts. Publish a
  compact top-N summary to `$GITHUB_STEP_SUMMARY` while keeping full data in
  downloadable artifacts.
- Record hotspots: log slowest pytest cases and slowest mutated modules; surface
  a top-10 table in future summaries for easy prioritisation.
- Include `schema_version` and allowlist counts in summaries so reviewers know
  at a glance whether contracts changed.

### Security & Governance
- Pin dependencies via `pip-compile` or `uv pip compile`; schedule automated
  refresh PRs that run all gates weekly.
- Upload SARIF results for additional static analysis tools (bandit, semgrep) so
  GitHub’s Security tab stays the authoritative view.
- Use branch protection + CODEOWNERS on `mutmut.ini`, `tools/`, and
  `docs/testing/` to guard key quality levers.

### Developer Ergonomics
- Keep the Makefile tidy: `.PHONY` targets, honour env overrides (`TOPN`,
  `REPORT_DEST`, `MUTATE_PATHS`), and provide `make help` with usage examples.
- Support dry-run modes (`DRY_RUN=1`) for scripts that otherwise mutate state or
  require GitHub connectivity.
- Create a short onboarding cheat sheet (“First PR” → run lint/type/test,
  `make mutants-report-local`, understand the mutation scoreboard, place new
  tests).

### Troubleshooting Quick Hits
- **Mutmut appears stuck:** increase `timeout`, narrow with `--paths-to-mutate`,
  confirm CPU load, resume via `mutmut rerun`.
- **Lots of 🤔/🙁 noise:** move module-level side effects under
  `if __name__ == "__main__":`, memoise expensive operations, mark genuine
  equivalents explicitly.
- **Hypothesis flaking:** use a `ci` profile (lower `max_examples`, adjust
  deadlines), archive failing blobs, rerun locally with the recorded seed/blob.

### Target Metrics

| Metric | Target (core) | Gate Strategy |
| --- | --- | --- |
| Unit tests passing | 100% | Hard |
| Coverage delta (touched modules) | ≥ −1.0% | Start soft, then hard |
| New mutation survivors in touched files | 0 | Start soft, then hard |
| Flaky tests in primary lane | 0 | Hard |
| Max CI wall time per job | ≤ 15–20 min | Monitor/soft |
