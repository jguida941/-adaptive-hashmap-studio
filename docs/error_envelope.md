# CLI Error Envelope

All CLI failures emit JSON on stderr with a stable exit code.

Envelope format:

```json
{"error": "<Code>", "detail": "...", "hint": "..."}
```

| Exit | Name       | When                                              |
|-----:|------------|---------------------------------------------------|
| 0    | OK         | Success                                           |
| 2    | BadInput   | CSV schema errors, invalid CLI flags, bad payload |
| 3    | Invariant  | Verification / consistency failures               |
| 4    | Policy     | Unsupported operations or contract breaches       |
| 5    | IO         | File or OS-level IO failures                      |

## Examples

```json
{"error":"BadInput","detail":"Missing header 'op' at line 1","hint":"See docs/workload_schema.md"}
```

Developers must route new failure paths through the shared helpers in `src/adhash/contracts/error.py`.

## Success Output (`--json`)

Pass `--json` to any CLI invocation to receive machine-readable success envelopes on stdout. The envelope always includes `ok: true` and the `command` name, with additional keys specific to the subcommand.

Examples:

```json
{"ok": true, "command": "put", "mode": "adaptive", "key": "K1", "value": "V1", "result": "OK"}
```

```json
{
  "ok": true,
  "command": "run-csv",
  "status": "completed",
  "csv": "data/workloads/w_uniform.csv",
  "total_ops": 100000,
  "final_backend": "robinhood",
  "summary": {"elapsed_seconds": 4.2, "ops_per_second": 23800.0, "migrations_triggered": 1}
}
```

Structured success output makes it easier to drive CI pipelines without scraping human-oriented text.
