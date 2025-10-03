# Prometheus & Grafana Integration

This guide explains how to scrape the CLI’s metrics with Prometheus and visualise them in Grafana, including example alert rules for the adaptive guardrails.

## 1. Start the CLI with Metrics Enabled

Expose the built-in `/metrics` and dashboard API while running a workload:

```bash
python hashmap_cli.py --mode adaptive run-csv \
  --csv data/workloads/w_uniform.csv \
  --metrics-port 9090 \
  --metrics-out-dir runs/metrics \
  --json-summary-out runs/summary.json
```

This binds the HTTP server to `http://localhost:9090/`, serving:

- `/metrics` – Prometheus text exposition
- `/api/metrics` – JSON view of the latest tick
- `/api/metrics/history?limit=100` – rolling history (mirrors `metrics.ndjson`)

## 2. Prometheus Scrape Configuration

Add the CLI to your Prometheus `scrape_configs` (replace host/port as needed):

```yaml
scrape_configs:
  - job_name: "adaptive-hashmap-cli"
    metrics_path: /metrics
    static_configs:
      - targets: ["localhost:9090"]
```

### Example Alert Rules

Guardrails rely on the exported metrics; the rules below mirror the CLI’s warnings:

```yaml
groups:
  - name: adaptive-hashmap-cli
    rules:
      - alert: HashMapHighLoadFactor
        expr: hashmap_load_factor > 0.90
        for: 30s
        labels:
          severity: warning
        annotations:
          summary: "Adaptive HashMap load factor high"
          description: "Load factor has stayed above 0.90 for 30s."

      - alert: HashMapProbeLength
        expr: hashmap_avg_probe_estimate > 6
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Average probe distance elevated"
          description: "Probe distance exceeded 6 slots for more than a minute."

      - alert: HashMapTombstones
        expr: hashmap_tombstone_ratio > 0.35
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Tombstone ratio high"
          description: "Robin Hood backend tombstones above 35%."
```

## 3. Grafana Dashboard

Import `docs/grafana_dashboard.json` into Grafana (Dashboards → Import). The dashboard ships with:

- Load factor and probe distance time-series panels
- Tombstone ratio
- Throughput (operations per second, derived using PromQL rate functions)
- Active guardrail alerts (uses Prometheus `alertmanager` data source or `hashmap_watchdog_alert_active` gauge)

## 4. Data Retention Tips

- Persist `metrics.ndjson` via `--metrics-out-dir` for offline analysis.
- Tune `--metrics-max-ticks` to throttle history size; this affects both `/api/metrics/history` and the NDJSON file.
- Use Prometheus recording rules to pre-compute hourly/daily aggregates if long-term trending is required.

## 5. Troubleshooting

- **No data in Grafana**: Confirm the Prometheus target is `UP` and that the CLI was launched with `--metrics-port`.
- **Guardrail alerts missing**: Ensure watchdog thresholds remain enabled (see `WATCHDOG_*` env vars) and add the alert gauge (`hashmap_watchdog_alert_active`) to dashboards.
- **Cross-origin errors**: Grafana scrapes Prometheus directly; no CORS support is required from the CLI. If you proxy the metrics endpoint, expose `/metrics` unchanged.

For more metric field details, see [`docs/metrics_schema.md`](metrics_schema.md).
