# Mutation Worktree Playbook

Running multiple mutation-scoped jobs in parallel is easier when each target
module has its own git worktree. This guide covers the recommended layout,
Makefile helpers, and how to coordinate several Codex/CLI sessions safely.

## Why Worktrees?

- **Isolation:** each worktree has independent `.mutmut-cache/`, `.hypothesis/`,
  and build artifacts—no cache collisions when Codex bots or teammates run
  different scopes simultaneously.
- **Shared history:** all worktrees point at the same `.git` store, so commits
  and branches stay in sync.
- **Parallelism:** you can dedicate a terminal (or Codex chat) to each lane and
  iterate without context switching.

## Directory Layout

```
repo/
├── .git/
├── src/
├── tools/
└── worktrees/
    ├── maps/
    ├── probing/
    └── snapshot/
```

The `worktrees/` folder is ignored by git and can be pruned/recreated at will.

## Quick Start (Makefile Helpers)

Set up the default lanes and run each mutation scope sequentially:

```bash
make mutants-run-lanes
```

What this does:

1. `make mutants-worktrees` provisions worktrees for the default lanes defined
   by `MUTANT_LANES` (`maps`, `probing`, `snapshot`).
2. For each lane it runs:
   - `mutmut run --paths-to-mutate <path> --use-coverage --jobs auto --timeout 8`
   - `tools/mutants_report.sh` (local-only) to drop
     `.mutmut-ci/survivors_report.md` inside the lane.

### Customising Lanes

Override `MUTANT_LANES`, `MUTANT_TIMEOUT`, or `MUTANT_JOBS` at invocation time:

```bash
MUTANT_LANES="maps=src/adhash/core/maps.py service=src/adhash/service" \
MUTANT_TIMEOUT=10 MUTANT_JOBS=4 make mutants-run-lanes
```

Each lane entry uses `name=paths_to_mutate`. Paths are passed directly to
`mutmut` and can include comma-separated modules.

### Running Lanes Manually

If you prefer manual control (e.g., one lane per Codex chat):

```bash
make mutants-worktrees

# Terminal / Chat A
cd worktrees/maps
mutmut run --paths-to-mutate src/adhash/core/maps.py --use-coverage --timeout 8
tools/mutants_report.sh MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file

# Terminal / Chat B
cd worktrees/probing
mutmut run --paths-to-mutate src/adhash/core/probing.py --use-coverage --timeout 8
tools/mutants_report.sh MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file

# Terminal / Chat C
cd worktrees/snapshot
mutmut run --paths-to-mutate src/adhash/core/snapshot.py --use-coverage --timeout 8
tools/mutants_report.sh MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file
```

### Example Multi-Chat Kickoff

When spinning up Codex sessions later, you can paste these prompts verbatim to
get each lane moving. Run `make mutants-worktrees` once beforehand.

- **Terminal / Chat A (maps lane)**
  ```text
  cd worktrees/maps
  mutmut run --paths-to-mutate src/adhash/core/maps.py --use-coverage --jobs auto --timeout 8
  tools/mutants_report.sh MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file
  ```
- **Terminal / Chat B (probing lane)**
  ```text
  cd worktrees/probing
  mutmut run --paths-to-mutate src/adhash/core/probing.py --use-coverage --jobs auto --timeout 8
  tools/mutants_report.sh MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file
  ```
- **Terminal / Chat C (snapshot lane)**
  ```text
  cd worktrees/snapshot
  mutmut run --paths-to-mutate src/adhash/core/snapshot.py --use-coverage --jobs auto --timeout 8
  tools/mutants_report.sh MUTANTS_LOCAL_ONLY=1 REPORT_DEST=file
  ```

After each run, open the lane’s `.mutmut-ci/survivors_report.md` and start
triaging mutants in that chat. When done, commit/tests from the worktree or run
`git worktree remove worktrees/<lane>` to reset it.

## Maintenance Commands

- Remove a lane: `git worktree remove worktrees/maps`
- Refresh from `main`: `git -C worktrees/maps pull --ff-only`
- Inspect status without leaving root: `git worktree list`

## Tips for Parallel Codex Sessions

1. **Name chats after lanes**: e.g., “Mutation maps lane”, “Mutation probing lane”.
2. **Share survivors reports**: each worktree writes `.mutmut-ci/` inside its
   folder; upload or copy the Markdown/JSON to a shared doc if multiple people
   collaborate.
3. **Commit from a worktree**: run `git status`, `git add`, `git commit` inside
   the lane. The commit appears in the main repo immediately.
4. **Cleanup regularly**: after merging a fix, run `git worktree remove` to
   avoid stale directories.

## Troubleshooting

- `git worktree add` fails with “already checked out”: add `-f` to force update
  (the Makefile does this automatically).
- Worktree out of sync with `main`: run `git fetch origin && git -C worktrees/<lane> reset --hard origin/main`.
- Mutation caches too large: delete `worktrees/<lane>/.mutmut-cache/` before the
  next run.

## Related Documentation

- `docs/ops/ci_cd_pipeline.md` – overall CI/mutation automation strategy.
- `docs/testing/mutation.md` – survivor triage workflow and tooling.
- `docs/testing/flaky_policy.md` – quarantine process for unstable tests.
- `tools/mutants_orchestrator.sh` – automated loop for running mutmut/report
  cycles with survivor thresholds, kill-rate goals, and dry-run mode.
