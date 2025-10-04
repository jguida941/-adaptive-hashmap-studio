# Batch Benchmark Runner

The batch runner executes a suite of `hashmap_cli.py` commands from a single TOML
specification and produces a Markdown report with results and command output
snippets. Use it to replay a consistent set of workloads across backends and
capture summary metrics without hand-running each CLI invocation. Mission
Control now exposes this workflow through the **Benchmark Suites** tab,
allowing you to browse specs, launch runs, and tail logs without leaving the
desktop UI. From there a dedicated **Workload DNA** tab renders bucket heatmaps
and collision-depth histograms for any analyzed job, making it easy to spot
skew before you hit “Run”.

## Specification format

Create a TOML file with a top-level `[batch]` table. Fields:

- `hashmap_cli` *(optional)* – path to `hashmap_cli.py`. Defaults to a file named
  `hashmap_cli.py` in the same directory as the spec.
- `report` *(optional)* – path for the generated Markdown report
  (default `reports/batch_report.md`).
- `html_report` *(optional)* – path for an accompanying HTML report.
- `jobs` – array of job tables. Each job supports:
  - `name` – label for the report table (defaults to `job-{index}`).
  - `command` – `"profile"` or `"run-csv"`.
  - `csv` – path to the workload CSV.
  - `mode` *(optional)* – backend mode (defaults to `"adaptive"`).
  - `json_summary` *(optional, run-csv only)* – where to write the summary JSON.
  - `latency_sample_k`, `latency_sample_every`, `metrics_out_dir` – forwarded to
    the CLI when present.
  - `extra_args` *(optional)* – additional CLI flags appended verbatim.

Example (`docs/examples/batch_baseline.toml`):

```toml
[batch]
hashmap_cli = "../../hashmap_cli.py"
report = "../../reports/batch_baseline.md"
html_report = "../../reports/batch_baseline.html"

[[batch.jobs]]
name = "profile-uniform"
command = "profile"
csv = "../../data/workloads/w_uniform.csv"

[[batch.jobs]]
name = "run-uniform"
command = "run-csv"
csv = "../../data/workloads/w_uniform.csv"
json_summary = "../../results/json/batch_uniform.json"
latency_sample_k = 2000
latency_sample_every = 64
```

## Running a batch

```bash
python -m adhash.batch --spec docs/examples/batch_baseline.toml
```

To discover bundled examples:

```bash
python -m adhash.batch --list
```

The repository currently ships `docs/examples/batch_baseline.toml` and
`docs/examples/batch_compaction.toml`. Copy one of these files and tweak the
paths to build a custom suite.

After completion the configured report path (in the example
`reports/batch_baseline.md`) contains a Markdown table summarising each job along
with a log appendix. Reports now include a **Comparative Summary** section that
pulls `ops_per_second` and latency metrics from the generated JSON summaries and
highlights the relative delta versus the fastest job. The HTML variant also embeds
a horizontal bar visualisation for quick scanning. If `html_report` is set an HTML
version is emitted in the same run. JSON summaries or metrics outputs requested in
the spec are produced alongside the report.

## Tips

- Paths inside the spec are resolved relative to the spec file. Use `..` to
  reference assets elsewhere in the repo.
- Jobs run sequentially using the current Python interpreter by default; pass
  `--python /path/to/python` to override.
- The Markdown report table includes throughput (`ops_per_second`) when the job
  writes a JSON summary containing that field.
