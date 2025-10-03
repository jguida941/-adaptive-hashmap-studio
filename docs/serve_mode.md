# Sticky Serve Mode

`hashmap_cli.py serve` keeps the dashboard and `/metrics` endpoint available without
running a workload inside the same process. Point it at an NDJSON source
(`metrics.v1` schema) to preload or tail historical ticks.

## Usage

```bash
# Terminal 1 – launch server and follow an NDJSON file
python hashmap_cli.py serve --port 9090 --source runs/metrics.ndjson --follow

# Terminal 2 – run workloads that write NDJSON ticks
python hashmap_cli.py --mode adaptive run-csv \
  --csv data/workloads/w_uniform.csv \
  --metrics-out-dir runs
```

Options:

- `--port` / `--host` – bind address for the dashboard (default `127.0.0.1:9090`).
- `--source` – metrics NDJSON file to load. Paths are resolved relative to the
  current working directory.
- `--follow` – keep tailing the file for new ticks (ideal when another process is
  appending to `metrics.ndjson`).
- `--history-limit` – limit the number of ticks retained for the dashboard chart
  buffers (default 360 samples).
- `--poll-interval` – how often to poll the source file when following.
- `GET /api/events` – new endpoint listing recent migrations/compactions; the
  dashboard presents these under “Recent Events.”
- `GET /api/metrics/histogram/latency` – JSON latency histogram buckets (per
  operation) backing the Plotly chart.
- `GET /api/metrics/histogram/probe` – JSON probe-length counts for the bar
  chart.
- `GET /api/metrics/heatmap` – Key-distribution heatmap matrix (down-sampled to
  at most 512 cells) used for the dashboard heatmap.

If `--source` is omitted, the server starts empty—useful for standalone demos or
external producers publishing ticks via other tooling.

Quick checks while the server is running:

```bash
curl http://127.0.0.1:9090/api/metrics/histogram/latency | jq '.operations.overall'
curl http://127.0.0.1:9090/api/metrics/histogram/probe | jq '.buckets'
curl http://127.0.0.1:9090/api/metrics/heatmap | jq '.rows, .cols, .total'
```

For ultra-fast workloads where latencies stay below 1 ms, run your replay with
`--latency-buckets micro` so the histogram endpoints expose finer-grained bins.
