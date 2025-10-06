# Probe Visualizer

Phase 4 introduces a probe-path tracing tool so you can inspect how individual operations traverse the hash map internals. The `probe-visualize` CLI command leverages the new `adhash.analysis.probe` module to capture every slot inspected during a GET or PUT.

## Quick Start

Visualise a GET against a snapshot:

```bash
python hashmap_cli.py --mode fast-lookup probe-visualize \
  --operation get \
  --key K42 \
  --snapshot snapshots/uniform.pkl.gz
```

Seed an ad-hoc map and trace a PUT without touching disk:

```bash
python hashmap_cli.py --mode fast-lookup probe-visualize \
  --operation put \
  --key K1 --value V1 \
  --seed A=alpha --seed B=beta
```

Add `--json` to obtain a machine-readable payload or `--export-json trace.json` to write the same data to disk (always indent=2).

## Output Anatomy

Text mode produces a succinct report:

```
Probe visualization [robinhood] GET key='K1'
Found: True | Terminal: match
Capacity: 64
Steps:
  Step 0: slot=5, state=occupied, key_repr='K1', matches=true
```

JSON mode nests the same information under `trace.path`, making it easy to drive UI components:

```json
{
  "backend": "robinhood",
  "operation": "get",
  "key_repr": "'K1'",
  "found": true,
  "terminal": "match",
  "path": [
    {"step": 0, "slot": 5, "state": "occupied", "matches": true}
  ]
}
```

## Options Reference

| Flag | Description |
| ---- | ----------- |
| `--operation {get,put}` | Required. Chooses the probe to trace. |
| `--key KEY` | Required. Target key. |
| `--value VALUE` | Required when `--operation put`. |
| `--snapshot PATH` | Load a snapshot (chaining, robinhood, or adaptive) prior to tracing. |
| `--seed KEY=VALUE` | Seed entries before tracing. Repeat the flag to add more. |
| `--export-json PATH` | Write the JSON trace to disk (indent=2). |
| `--apply` | Apply the operation to the in-memory map after tracing. |

The command honours the global `--mode` flag when no snapshot is provided (`fast-lookup` instantiates a Robin Hood map, `fast-insert` picks chaining, etc.).

## Mission Control & TUI Integration

- **Mission Control** now includes a “Probe Visualizer” tab. Drop in a JSON file exported from the CLI (or run the CLI with `--json` inside the embedded Run Command panel) to see probe paths rendered instantly.
- **Textual TUI** accepts `--probe-json /path/to/trace.json` and binds **`p`** to reload the file while the dashboard runs. This is handy for side-by-side inspection alongside live metrics.

## Testing & Automation

Unit coverage lives in `tests/test_probe_tracer.py`; CLI contracts are enforced by `tests/test_cli_probe_command.py`. Run `pytest -q` to exercise both suites. The new module is exposed under `adhash.analysis` for direct import in notebooks or experiment scripts.
