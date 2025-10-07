# Flaky Test Quarantine Policy

Flaky tests erode signal and slow teams down. This policy outlines how to
identify, quarantine, and retire flaky cases without masking real failures.

## Identifying Flakies

Flag any test that fails intermittently without a code change. Before tagging
the test:

1. Reproduce locally with `pytest --maxfail=1 --lf` to confirm the failure is
   nondeterministic.
2. Capture the stdout/stderr and any relevant logs; attach them to the tracking
   issue or PR.

## Quarantining a Test

1. Add `@pytest.mark.flaky` (or an equivalent marker) to the test.
2. Move the test into the `flaky` Pytest marker group so it can run in a
   non-blocking CI lane.
3. Update the test’s docstring (or a nearby comment) with a link to the tracking
   issue that owns the fix.

The main CI workflow must *not* run flaky tests; instead, add or update a
secondary workflow that executes `pytest -m flaky` and reports results without
affecting the PR status.

## Fix Expectations

Quarantined tests are a temporary measure. Owners should:

1. Triage the root cause within **2 business days**.
2. Submit a fix (or disablement plan) within **1 sprint**. If additional time is
   needed, update the tracking issue with the revised ETA.
3. Remove the flaky marker and restore the test to the main lane once the fix is
   verified.

## Preventing Flakiness

- Avoid static/shared global state; use fixtures that isolate state per test.
- For async or threaded code, wait on explicit signals rather than `sleep`.
- Prefer deterministic seeds (`random.seed`, `numpy.random.default_rng`) when
  randomness is required.

## Escalation

If a flaky test remains quarantined beyond the expected window, the owning team
should raise visibility in the #quality channel and either prioritise the fix or
agree on a different mitigation (e.g., removal, rewrite).
