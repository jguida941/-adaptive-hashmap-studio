# Workload CSV Schema

Workload files are comma-separated with a mandatory header:

```
op,key,value
```

- `op`: one of `put`, `get`, `del` (case-insensitive).
- `key`: non-empty string for the target key.
- `value`: required column. For `put` rows it must be non-empty; for `get` and `del` rows leave the field blank (`,` at the end).

Additional guidelines:
- The file must use UTF-8 encoding with Unix newlines.
- Duplicate keys are allowed; they are processed in order.
- Comments or extra columns are not supported.
- Very large workloads can be guarded with `--csv-max-rows` and `--csv-max-bytes` (defaults clamp to protect memory). Set either flag to `0` to disable the respective check.
- Use `run-csv --dry-run --csv your.csv` to validate a workload without executing it; the CLI will surface detailed row/column diagnostics when something is wrong.

Validation errors in the CLI surface as JSON error envelopes with hints pointing back to this document.
