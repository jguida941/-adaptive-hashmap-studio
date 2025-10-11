# Mutation Coverage Progress

This log captures the ongoing work to reduce `mutmut` survivors and timeouts across the Adaptive Hash Map CLI.

## Completed Work
- **Robin Hood map compaction** (`src/adhash/core/maps.py`): Compaction now triggers whenever the tombstone ratio meets the configured threshold, eliminating the Hypothesis race that previously lost entries.
- **Latency hygiene** (`src/adhash/metrics/core.py`): `apply_tick_to_metrics` ignores NaN histogram buckets and sanitises questionable latency or alert data before it reaches consumers.
- **CLI registration coverage** (`tests/test_cli_commands_register.py`): Every subcommand is verified to be registered and guard-wrapped, preventing missing entry points or unhandled imports.
- **CLI handlers coverage** (`tests/test_cli_commands_handlers.py`): Adds direct tests for the `ab-compare` command, covering artifact path resolution, `--no-artifacts`, and the success emitter.
- **Mutation digest utility** (`tools/mutmut_digest.py`): Converts `.mutmut-ci/mutmut_results.txt` into a structured JSON summary (`.mutmut-ci/mutmut_summary.json`) to surface survivors/timeouts per module.
- **Metrics server regressions** (`tests/test_metrics_endpoints.py`):
  - Verifies `/api/metrics` headers, gzip negotiation, and content length to constrain `_set_common_headers`.
  - Exercises `history_buffer` fallback, event limit clamping, `OPTIONS` CORS responses, and static asset sandboxing to shake out long-standing survivors.
- **Metrics server unit harness** (`tests/test_metrics_server_unit.py`): Creates stub HTTPServer/handler scaffolding so `_client_supports_gzip`, `_write_body`, `_limit`, and `_authorized` logic can be mutation-tested without binding sockets.
  - Latest additions cover summary fallbacks, comparison payload responses, and history/limit edge cases to kill surviving mutants in `start_metrics_server`.
- **Regression guard** (`pytest --ignore=mutants --ignore=worktrees`): Full suite passes after the cleanup fixes, confirming the baseline before the next `mutmut run`.

## Current Hotspots
Source: artifact `18321148363` (`.mutmut-ci/mutmut_results.txt`).

| Module | Survivors | Timeouts |
| --- | ---: | ---: |
| `adhash.cli.commands` | 1,223 | 296 |
| `adhash.metrics.core` | 545 | 119 |
| `adhash.metrics.server` | 487 | 108 |
| `adhash.analysis.probe` | 354 | 88 |
| `adhash.workloads.dna` | 319 | 77 |
| `adhash.service.jobs` | 211 | 52 |
| `adhash.tui.app` | 185 | 48 |
| `adhash.core.maps` | ~173 | ~44 *(bug above already fixed)* |

## Workflow Checklist
1. Run `python tools/mutmut_digest.py` to refresh the JSON snapshot used in dashboards.
2. Execute the targeted pytest suites (CLI, metrics core, metrics endpoints) to confirm coverage holds.
3. Iterate on each hotspot with a scoped mutation pass, e.g.:
   ```bash
   MUTATE_PATHS=src/adhash/metrics/server.py mutmut run --max-children 4
   ```
   Re-run after each test/logic addition until survivors drop.
4. Once the major modules are tamed, run the full `mutmut run` without scoping and upload the artifact for tracking.

## Open Items
- Kill the remaining `adhash.metrics.server` survivors now that coverage enforces header/limit behaviour.
- Tackle high-volume survivors in `adhash.metrics.core` and `adhash.cli.commands` with focused tests.
- Refresh the artifact (`make mutants-report`) after notable progress so CI dashboards and this log stay in sync.
