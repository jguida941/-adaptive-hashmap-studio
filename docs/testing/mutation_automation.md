# Mutation Automation Loop

The `tools/mutants_orchestrator.sh` script automates the “run mutmut → inspect
survivors → scaffold tests” loop until a desired kill rate or survivor cap is
reached. Combine it with worktrees to let multiple Codex sessions triage
different modules in parallel.

## Quickstart

```bash
# Preview survivors without running mutmut or writing tests
make mutants-dryrun

# Run the orchestration loop for maps.py until kill-rate ≥ 70% or survivors ≤ 50
make mutants-auto

# Sweep core modules sequentially with shared settings
make mutants-core
```

## Stop Criteria

Each iteration performs:

1. `pytest -q` (warms coverage for mutmut).
2. `mutmut run --paths-to-mutate <module> --use-coverage --jobs auto --timeout <t>`.
3. `tools/mutants_report.sh TOPN=<N> REPORT_DEST=file` to regenerate survivor
   reports.
4. Scoreboard parsing to compute:
   - `kill-rate = killed / (killed + survived)`.
   - `survivors` (from mutmut results / report JSON).
5. **If live mode**: create/update TODO scaffolds under
   `tests/mutation_todos/` for mutants whose `file` matches the module. Each
   scaffold is marked with `pytest.mark.mutation_todo` and includes the diff.
6. Optional `mutmut run` rerun (skipped in dry-run) to measure improvement.

The loop finishes when any of the following holds:

- Kill rate ≥ `--target-kill` (default 0.70)
- Survivors ≤ `--survivors-cap` (default 50)
- Iterations ≥ `--max-iterations`

Use `--dry-run` to generate `.proposed` files under
`tests/mutation_todos/_proposed/` without touching live tests.

## Scope Tips

- Start with `src/adhash/core/maps.py` to stabilise the highest-value mutants.
- For directory-level sweeps, pass a comma-separated list via
  `--mutate-arg '--paths-to-mutate path_a,path_b'` or add modules to
  `make mutants-core`.
- Always run within a worktree (`make mutants-worktrees`) when coordinating
  multiple Codex sessions so caches stay isolated.

## Noise & Safety Controls

- Mark true equivalent mutations with `# pragma: no mutate` only after codeowner
  review; track allowlisted mutants in a small text file next to the module.
- If the orchestrator generates scaffolds that still flake, wrap them with
  `pytest.mark.flaky` temporarily and follow the
  [flaky policy](flaky_policy.md).
- Capture diffs from `.mutmut-ci/survivors_report.md` and share them when
  requesting help from Codex or teammates.

## Script Reference

```
tools/mutants_orchestrator.sh --module <path> [options]

Options:
  --module PATH            Target module/file (required)
  --target-kill FLOAT      Kill-rate threshold (default 0.70)
  --survivors-cap INT      Survivor threshold (default 50)
  --max-iterations INT     Loop limit (default 3)
  --timeout INT            Mutmut timeout seconds (default 8)
  --jobs N                 Mutmut --jobs value (default auto)
  --topn INT               Top survivors to report (default 25)
  --dry-run                Generate proposals only
  --mutate-arg ARG         Extra mutmut argument (repeatable)
```

Artifacts per iteration:

- `.mutmut-ci/survivors_report.md` / `.json` (schema_version=1)
- `.mutmut-ci/github_step_summary.md` (scoreboard snippet)
- Live scaffolds `tests/mutation_todos/test_<module>_<id>.py` *or*
  proposals under `tests/mutation_todos/_proposed/`

Combine this automation with the broader
[mutation worktree playbook](../ops/mutation_worktrees.md) and
[CI/CD pipeline guide](../ops/ci_cd_pipeline.md) to keep the loop fast and
disciplined.
