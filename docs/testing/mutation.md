# Mutation Testing Triage

Mutation testing runs continuously in CI (see `mutation-tests.yml`). The
workflow uploads a `mutmut-results` artifact that mirrors the terminal
dashboard (🎉 killed, 🫥 survived, ⏰ timeout, 🙁 suspicious, 🔇 skipped).
The scoreboard helps track progress: aim to keep 🎉 increasing while 🫥 and
🙁 decline over time.

To streamline local triage, use the helper script:

```bash
# Fetch the latest artifact (if gh is available), rebuild the survivors report,
# and generate TODO test skeletons for each module.
make mutants-report          # writes .mutmut-ci/survivors_report.md

# Same but stay offline and print to stdout.
make mutants-report-local    # skips gh, still generates TODO stubs
```

The script lives at `tools/mutants_report.sh`. In addition to the Markdown
report, it emits a machine-readable `.mutmut-ci/survivors_report.json` (schema
versioned) and a short `.mutmut-ci/github_step_summary.md` snippet that CI
pipes into `$GITHUB_STEP_SUMMARY`.

Configuration is handled via environment variables:
environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `WORKFLOW` | `mutation-tests.yml` | GitHub Actions workflow to poll |
| `ART_NAME` | `mutmut-results` | Artifact name to download |
| `OUTDIR` | `.mutmut-ci` | Local working directory for generated files |
| `TOPN` | `25` | Number of survivors to embed in the Markdown report |
| `REPORT_DEST` | `file` | Where to publish the report (`file`, `stdout`, `issue`, `pr`, or `none`) |
| `MUTANTS_LOCAL_ONLY` | `0` | Set to `1` to skip artifact downloads entirely |
| `PYTHON_BIN` | `python3` | Interpreter to use for installing/running `mutmut` |
| `SKIP_MUTMUT_INSTALL` | `0` | Set to `1` if the environment already has `mutmut`/`pytest` |

`REPORT_DEST=issue` opens or updates a tracking issue. `REPORT_DEST=pr` posts a
PR comment when run inside a pull request context. By default the script simply
writes `.mutmut-ci/survivors_report.md`.

When survivors exist, the script also drops placeholder tests under
`tests/mutation_todos/`. Each test is marked with `@pytest.mark.mutation_todo`
and skips automatically—replace the placeholder with assertions that kill the
specific mutant shown in the report.

## Triage Playbook

1. Run `make mutants-report` (or download `mutmut-results` from Actions and run
   the script manually).
2. Open `.mutmut-ci/survivors_report.md`. Target one survivor diff at a time—
   paste the snippet into a new Codex/ChatGPT chat and ask for a focused
   pytest that fails under the mutant and passes otherwise.
3. Replace the placeholder TODO test with the real assertions.
4. Commit the new test, rerun `mutmut run` locally (or let CI handle it), and
   verify that the survivor count drops. Repeat until the scoreboard shows
   progress.

### Scope control

While iterating on a hotspot, narrow the mutation scope in `mutmut.ini`:

```ini
[mutmut]
paths_to_mutate = src/adhash/core
tests_dir = tests
runner = env PYTHONPATH=src python -m pytest -q
use_coverage = 1
timeout = 5
```

Override the scope temporarily by setting `paths_to_mutate` or by exporting
`MUTATE_PATHS` before invoking `mutmut run`. Restore the broader scope before
merging to keep CI honest.

### Marking known equivalents

Mutants that cannot be killed because they preserve behaviour should be marked
with `# pragma: no mutate`. Document the rationale alongside the pragma so
future maintainers know why the mutation remains equivalent.

## CI Integration Tips

- Publish both `mutmut_results.txt` and `survivors.md` as job artifacts to
  keep the local tooling contract stable.
- Append a compact survivors summary to `$GITHUB_STEP_SUMMARY` so the dashboard
  is visible inside PRs.
- During adoption, keep the mutation step non-blocking (report-only). Once the
  backlog shrinks, gate on `survivors_delta` for files touched in the PR.
- Consider a pre-commit hook that warns (non-blocking) when a commit modifies
  files with known survivors, nudging contributors to add tests.
