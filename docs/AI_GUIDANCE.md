# docs/AI_GUIDANCE.md
# (no TOC; meant for copy-pasting into prompts)

> TL;DR for agents
- Install with lock: `uv pip install -e ".[dev]" --locked` (requires committed `uv.lock`)
- Run PR profile: set `USE_XDIST=1`, then `./scripts/pipeline.sh --mode fast`
- Nightly/full parity: `./scripts/pipeline.sh --mode full`
- Security: any HIGH/CRIT from Semgrep, Bandit, Grype, Trivy, or pip-audit is a hard fail
- Mutation: PR pipeline scopes to `$MUTATE_PACKAGES`; nightly runs the full sweep

---

## Local Gauntlet
- Install dependencies via `uv pip install -e ".[dev]" --locked`; the lockfile must stay committed.

## Stage-Gated Workflow
1. **Plan**
2. **Implement with Guardrails**
   - When `mutmut` runs on PRs, scope to touched packages via `$MUTATE_PACKAGES` (automatically exported by the pipeline).
3. **Validate**
4. **Summarise**

## CI Integration Expectations

### FAST (PRs)
- Before invoking the fast pipeline, set `USE_XDIST=1` to enable pytest-xdist locally.
- Run `./scripts/pipeline.sh --mode fast`.

### FULL (main/nightly)
- Run `./scripts/pipeline.sh --mode full`; coverage from parallel workers is merged automatically via `coverage combine`.

## Security-First Prompt
- Ensure Semgrep fixes satisfy the policies in `.semgrep.yml` (timeouts for subprocess/requests, safe deserialization) and remain triaged.
- Security findings (HIGH/CRIT) from Semgrep, Bandit, Grype, Trivy, pip-audit must be resolved—do not silence or downgrade them.

## PR Discipline
- Never skip tests, and never lower `COV_MIN`, `MUT_MIN`, or security thresholds just to get green; fix the underlying issue instead.
- Keep diffs scoped and stage related changes together.

## Coding Guardrails Checklist
- Unit + integration tests must pass locally.
- Imports for the public packages (`adhash`, `hashmap_cli`) must succeed.
- CLI smoke test must succeed: `hashmap-cli --help` in a clean virtualenv.
- No stray print/debug logging; follow the logger patterns.

## Test Design Checklist
- Tests must be deterministic (control random seeds / Hypothesis profiles).
- Update golden files only with the explicit regeneration flag, and note “golden refresh” in the commit message or PR description.
- Prefer targeted mutation runs (`MUTATE_PATHS=... mutmut run`) when iterating on large modules.

## Reference Commands
- Full lint/format pass: `./scripts/pipeline.sh --mode lint`
- Refresh mutation summary artifact: `python tools/mutmut_digest.py`
- Fast suite with xdist: `USE_XDIST=1 ./scripts/pipeline.sh --mode fast`

## Contact
Ping @platform-tooling in Slack for pipeline or CI questions.
