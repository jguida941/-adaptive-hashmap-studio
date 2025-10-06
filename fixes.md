# Mission Control Fix Log

This log collects the regression issues uncovered after the widget modularisation, plus the status of the fixes that still need to land before the UI is production-worthy. Each entry captures what is broken, how to reproduce, the root cause (as observed in the current code base), and the fix strategy.

## 1. Workload DNA heatmap orientation mismatch
- **Symptom**: Bucket `0x000` appears in the top-left corner in the DNA view but bottom-left in the Metrics view. Hover tooltips report the wrong bucket ID.
- **Reproduce**: Open Workload DNA → switch to *Heatmap* → compare with Metrics heatmap or hover hotspots in a known dataset.
- **Root cause**: `src/adhash/mission_control/widgets/workload_dna.py:352` transposes the grid (`grid.T`) while keeping `plot.invertY(False)`. Metrics uses `invertY(True)` with the original orientation.
- **Fix**: Stop transposing, call `invertY(True)`, and recalc hover indices row-major. Also disable the “Top buckets” spin box outside the bucket modes so it doesn’t look broken.
- **Status**: Fixed in current branch (needs in-app verification).

## 2. Telemetry heatmap renders as a tiny postage stamp
- **Symptom**: Metrics heatmap draws but the viewbox stays zoomed out; image occupies a small corner.
- **Reproduce**: Run telemetry with a non-trivial heatmap payload; observe the plot area.
- **Root cause**: `_update_heatmap` updates the `ImageItem` but never sets the view box range to `(0..cols, 0..rows)` or calls `autoRange`.
- **Fix**: After `setImage`, call `self._heatmap_plot.getViewBox().setRange(...)` (or `autoRange`) based on the array shape.
- **Status**: Fixed (awaiting telemetry smoke test in the UI).

## 3. Benchmark suite discovery never finishes in the live app
- **Symptom**: “Discover” stays in a spinning state forever.
- **Reproduce**: Open Benchmark Suites pane → click *Discover*.
- **Root cause**: The previous threading helper wasn’t cancel-safe. We now submit work via a `ThreadPoolExecutor`, but `_discover_specs` may still block if it hits large directories. Need to guard long scans and ensure cancellation resets state promptly.
- **Fix**:
  1. Confirm the executor path returns on the main thread (already wired) and measure `_discover_specs` cost. If it’s hitting broad globs, restrict search roots or add early exit.
  2. Tie `cancel_discovery` to the active future (already partially done) and show completion/cancellation status in the UI.
- **Status**: Fixed; discovery callbacks now emit through a Qt signal bridge so the initial auto-refresh completes even when the event loop starts after the worker returns.

## 7. TUI stuck on "Waiting for metrics"
- **Symptom**: `python -m adhash.tui --metrics-endpoint …` never populates data, even while `run-csv --metrics-port …` is active.
- **Root cause**: The metrics HTTP server always gzipped JSON payloads regardless of the client's `Accept-Encoding`. The Textual client did not request gzip, so it received compressed bytes, failed to decode them, and treated the response as empty.
- **Fix**: Make the server respect `Accept-Encoding`—gzip responses only when the header advertises support, fall back to identity encoding otherwise.
- **Status**: Fixed; TUI now renders metrics as soon as the endpoint is live.

## 4. Run Command builder UX validation
- **Symptom**: Builder fields might not reflect controller-driven changes (e.g., when the config editor saves a preset). Needs human validation.
- **Root cause**: We parse/compose with `shlex`, but the controller still only calls `apply_config_path`. Works in tests, but verify *in app* that the builder updates when baseline configs/presets change.
- **Fix**: Manual QA plus instrumentation if discrepancies show up.
- **Status**: QA pending.

## 5. Theming cohesion (inline vs. stylesheet)
- **Symptom**: Plot frames briefly lost styling when the QSS was missing.
- **Root cause**: We now load `widgets/styles.qss`. If the resource is not packaged, the fallback is the old inline stylesheet.
- **Fix**: Ensure packaging copies `styles.qss` (e.g., via `package_data`) and keep the fallback. No code changes needed beyond packaging config.
- **Status**: Need packaging follow-up.

## 6. Automated regression coverage
- **New tests**: `tests/test_mission_control_widgets_qt.py` now covers the run-command builder sync and discovery cancellation.
- **Still missing**: Unit coverage for histogram helpers (`extract_latency_histogram`, etc.) and heatmap orientation. Add parameterised tests to catch future regressions.

## Next Validation Pass
1. Launch Mission Control locally.
2. Verify suite discovery completes (and cancel works) with real files.
3. Confirm heatmap orientation fix after committing the patch.
4. Exercise run-command builder with configs/presets in the actual UI.

All fixes above remain staged in-source; once the open items are resolved, update this log with commit hashes and close out the audit.
