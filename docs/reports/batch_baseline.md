# Adaptive Hash Map Batch Report

Generated: 2025-10-02 18:22:50

| Job | Command | Status | Duration (s) | Ops/s | Backend |
|---|---|---|---:|---:|---|
| profile-uniform | profile | ❌ | 0.05 | - | - |
| run-uniform | run-csv | ✅ | 20.21 | 4,962 | chaining |

## Job Logs
### profile-uniform

```text
usage: hashmap_cli.py [-h]
                      [--mode {fast-insert,fast-lookup,memory-tight,adaptive}]
                      [--log-json] [--log-file LOG_FILE]
                      [--log-max-bytes LOG_MAX_BYTES]
                      [--log-backup-count LOG_BACKUP_COUNT] [--json]
                      [--config CONFIG]
                      {put,get,del,items,profile,generate-csv,run-csv,compact-snapshot,verify-snapshot}
                      ...
hashmap_cli.py: error: unrecognized arguments: --mode adaptive
```

### run-uniform

```text
2025-10-02T18:22:30 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-02T18:22:50 [INFO] hashmap_cli: run-csv finished in 20.153454 s, backend=chaining
2025-10-02T18:22:50 [INFO] hashmap_cli: Wrote JSON summary: /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/results/json/batch_uniform.json
```
