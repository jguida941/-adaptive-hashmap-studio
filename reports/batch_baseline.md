# Adaptive Hash Map Batch Report

Generated: 2025-10-05 02:47:59

| Job | Command | Status | Duration (s) | Ops/s | Backend |
|---|---|---|---:|---:|---|
| profile-uniform | profile | ✅ | 0.06 | - | - |
| run-uniform | run-csv | ✅ | 76.53 | 1,308 | chaining |

## Comparative Summary

| Job | Ops/s | Δ vs. max | p99 latency (ms) |
|---|---:|---:|---:|
| run-uniform | 1,308 | 0.0% | 5.871 |

<div class="ops-chart">
<div class="ops-bar"><span class="ops-label">run-uniform</span><div class="ops-track"><div class="ops-fill" style="width:100.0%"></div></div><span class="ops-value">1,308 ops/s</span></div>
</div>

## Job Logs
### profile-uniform

```text
fast-insert
```

### run-uniform

```text
2025-10-05T02:46:42 [INFO] hashmap_cli: Adaptive map started on chaining
2025-10-05T02:47:59 [INFO] hashmap_cli: run-csv finished in 76.464104 s, backend=chaining
2025-10-05T02:47:59 [INFO] hashmap_cli: Wrote JSON summary: /Users/jguida941/Dev/GitHubProject/AdaptiveHashMapCli/results/json/batch_uniform.json
```
