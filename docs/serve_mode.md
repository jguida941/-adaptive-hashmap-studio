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
- `--compare` – optional comparison JSON produced by `ab-compare`; the dashboard
  adds a summary strip showing throughput and latency deltas (candidate vs baseline).
  When you use `ab-compare --out-dir <dir>` the CLI writes `comparison.json` and
  `comparison.md` alongside the `artifacts/` directory, so you can reference
  `<dir>/comparison.json` directly.
- `GET /api/events` – new endpoint listing recent migrations/compactions; the
  dashboard presents these under “Recent Events.”
- `GET /api/metrics/histogram/latency` – JSON latency histogram buckets (per
  operation) backing the Plotly chart.
- `GET /api/metrics/histogram/probe` – JSON probe-length counts for the bar
  chart.
- `GET /api/metrics/heatmap` – Key-distribution heatmap matrix (down-sampled to
  at most 512 cells) used for the dashboard heatmap.
- Health probes: `GET /healthz` and `GET /readyz` return gzip-compressed JSON
  (`{"schema": "metrics.health.v1", "status": "ok"}`) so you can plug the
  server into Kubernetes, Nomad, or simple cron probes.

Security & headers:

- The server now emits `Cache-Control: no-store`, `Vary: Accept-Encoding`, and
  `Content-Encoding: gzip` on every `/api/*` response. Clients should always
  decompress gzip responses (Python `requests` does this automatically).
- Set `ADHASH_TOKEN=<secret>` before launching `serve` (or any `run-csv` with
  `--metrics-port`) to require `Authorization: Bearer <secret>` on every API
  call. The Mission Control poller and the dashboard JS honour the token when
  present.
- Throughput smoothing is exposed via `ADHASH_OPS_ALPHA` (default `0.25`). Lower
  values smooth more aggressively; higher values react faster.

If `--source` is omitted, the server starts empty—useful for standalone demos or
external producers publishing ticks via other tooling.

Quick checks while the server is running:

```bash
curl --compressed http://127.0.0.1:9090/api/metrics | jq '.schema, .ops_per_second_ema'
curl --compressed http://127.0.0.1:9090/api/metrics/histogram/latency | jq '.operations.overall'
curl --compressed http://127.0.0.1:9090/api/metrics/histogram/probe | jq '.buckets'
curl --compressed http://127.0.0.1:9090/api/metrics/heatmap | jq '.rows, .cols, .total'
curl --compressed http://127.0.0.1:9090/api/compare | jq '.diff.ops_per_second'
curl --compressed http://127.0.0.1:9090/healthz | jq
```

For ultra-fast workloads where latencies stay below 1 ms, run your replay with
`--latency-buckets micro` so the histogram endpoints expose finer-grained bins.
