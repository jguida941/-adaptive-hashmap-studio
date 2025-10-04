# Adaptive Hash Map Batch Report

Generated: 2025-10-04 06:58:56

| Job | Command | Status | Duration (s) | Ops/s | Backend |
|---|---|---|---:|---:|---|
| profile-uniform | profile | ✅ | 0.07 | - | - |
| run-uniform | run-csv | ✅ | 80.17 | 1,248 | chaining |

## Comparative Summary

| Job | Ops/s | Δ vs. max | p99 latency (ms) |
|---|---:|---:|---:|
| run-uniform | 1,248 | 0.0% | 6.100 |

<div class="ops-chart">
<div class="ops-bar"><span class="ops-label">run-uniform</span><div class="ops-track"><div class="ops-fill" style="width:100.0%"></div></div><span class="ops-value">1,248 ops/s</span></div>
</div>

## Job Logs
### profile-uniform

```text
fast-lookup
```

### run-uniform

```text
2025-10-04T06:57:36 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-04T06:58:56 [INFO] hashmap_cli: run-csv finished in 80.107788 s, backend=chaining
2025-10-04T06:58:56 [INFO] hashmap_cli: Wrote JSON summary: /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/results/json/batch_uniform.json
```
