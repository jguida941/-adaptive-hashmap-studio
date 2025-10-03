# Metrics Tick Schema v1

Contract: every emitted tick **must** include `"schema": "metrics.v1"` and the fields below.

```json
{
  "schema": "metrics.v1",
  "t": 0.0,
  "backend": "robinhood",
  "ops": 2000,
  "ops_by_type": {"put": 469, "get": 1400, "del": 131},
  "migrations": 0,
  "compactions": 0,
  "load_factor": 0.53,
  "max_group_len": 2.0,
  "avg_probe_estimate": 0.0,
  "tombstone_ratio": 0.12,
  "probe_hist": [[0, 533], [1, 87]],
  "latency_ms": {
    "overall": {"p50": 0.08, "p90": 0.12, "p99": 0.20},
    "put": {"p50": 0.09, "p90": 0.13, "p99": 0.21},
    "get": {"p50": 0.07, "p90": 0.10, "p99": 0.18},
    "del": {"p50": 0.08, "p90": 0.11, "p99": 0.19}
  },
  "latency_hist_ms": {
    "overall": [
      {"le": 0.10, "count": 120},
      {"le": 0.50, "count": 498},
      {"le": 1.00, "count": 750},
      {"le": "+Inf", "count": 800}
    ],
    "put": [
      {"le": 0.25, "count": 80},
      {"le": 0.50, "count": 140},
      {"le": "+Inf", "count": 170}
    ]
  },
  "alerts": [
    {
      "metric": "load_factor",
      "value": 0.95,
      "threshold": 0.90,
      "severity": "warning",
      "backend": "chaining",
      "message": "Load factor guardrail exceeded: 0.950 ≥ 0.900"
    }
  ],
  "events": [
    {"type": "switch", "from": "chaining", "to": "robinhood", "t": 0.95},
    {"type": "compaction", "backend": "robinhood", "source": "proactive", "t": 1.25}
  ]
}
```

## Compatibility Rules

- Additive-only changes are permitted within v1 (new optional fields or labels).
- Any required-field change or incompatible semantics must bump to `metrics.v2` and update tests + docs.

## Acceptance Checklist

- NDJSON output contains `"schema": "metrics.v1"` on every line.
- `load_factor` stays within `[0, 1]` and latency percentiles obey `p50 ≤ p90 ≤ p99`.
- `tombstone_ratio` reflects the RobinHood backend (0.0 when chaining).
- When probe histograms are present, sum of counts matches sampled operations (within tolerance).
- `latency_ms` is the canonical field; `latency_ns` is kept for backwards compatibility but will be removed in v2.
- `alerts` (when present) list active guardrails; each object includes `metric`, `value`, `threshold`,
  and `severity` so dashboards and alerting systems can render consistent banners.
- `latency_hist_ms` exposes cumulative bucket counts (matching Prometheus histograms) so Grafana panels
  can visualise the same data as `/metrics`; the final entry must use `"+Inf"` for the open-ended bucket.
