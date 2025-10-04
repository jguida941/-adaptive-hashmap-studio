# Contributing

## Definition of Ready (attach to issues)
- Goal and scope described in one sentence.
- Impacted contracts checked: metrics.v1 / error envelope / snapshot format.
- Acceptance criteria: unit + CLI contract tests, docs updated, perf budget respected.
- Constraints listed (allowed deps, no sleeps >100ms, no network in tests).
- Test data identified (mini workload ≤200 rows with valid + invalid variants).

## Pull Request Requirements
- Run `make lint type test smoke` locally and paste command summaries in the PR.
- Check the contract boxes in the PR template; bump schema/version when breaking.
- Update docs under `docs/` whenever behavior visible to users changes.
- Add or update tests alongside code (unit, property, CLI contract, snapshot).

## Local Setup

```bash
make setup
pre-commit install
```

Happy hacking!
