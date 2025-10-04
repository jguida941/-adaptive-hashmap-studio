# Adaptive Hash Map Batch Report

Generated: 2025-10-04 04:57:45

| Job | Command | Status | Duration (s) | Ops/s | Backend |
|---|---|---|---:|---:|---|
| profile-skew | profile | ✅ | 0.06 | - | - |
| run-skew-compaction | run-csv | ✅ | 53.86 | 1,859 | chaining |

## Comparative Summary

| Job | Ops/s | Δ vs. max | p99 latency (ms) |
|---|---:|---:|---:|
| run-skew-compaction | 1,859 | 0.0% | 3.044 |

<div class="ops-chart">
<div class="ops-bar"><span class="ops-label">run-skew-compaction</span><div class="ops-track"><div class="ops-fill" style="width:100.0%"></div></div><span class="ops-value">1,859 ops/s</span></div>
</div>

## Job Logs
### profile-skew

```text
fast-lookup
```

### run-skew-compaction

```text
2025-10-04T04:56:52 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-04T04:57:45 [INFO] hashmap_cli: run-csv finished in 53.805253 s, backend=chaining
2025-10-04T04:57:45 [INFO] hashmap_cli: Wrote JSON summary: /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/results/json/batch_compaction.json
```
