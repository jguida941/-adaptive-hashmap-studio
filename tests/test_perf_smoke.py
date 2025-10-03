import json
import subprocess
import sys
from pathlib import Path


CLI = [sys.executable, "hashmap_cli.py"]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, check=True, capture_output=True)


def test_run_csv_perf_smoke(tmp_path: Path) -> None:
    workload = tmp_path / "smoke.csv"
    summary_path = tmp_path / "summary.json"
    metrics_dir = tmp_path / "metrics"

    # Generate a tiny workload to keep runtime fast while stressing the pipeline.
    run(
        CLI
        + [
            "generate-csv",
            "--outfile",
            str(workload),
            "--ops",
            "200",
            "--read-ratio",
            "0.7",
            "--key-skew",
            "0.3",
            "--key-space",
            "128",
            "--seed",
            "123",
        ]
    )

    completed = run(
        CLI
        + [
            "--mode",
            "adaptive",
            "run-csv",
            "--csv",
            str(workload),
            "--json-summary-out",
            str(summary_path),
            "--metrics-out-dir",
            str(metrics_dir),
            "--metrics-max-ticks",
            "32",
        ]
    )

    # Ensure the CLI succeeded and emitted a JSON summary with throughput details.
    assert completed.returncode == 0
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["total_ops"] == 200
    assert data["ops_per_second"] is None or data["ops_per_second"] > 0
    assert data["final_backend"] in {"chaining", "robinhood", "memory-tight", "adaptive"}

    # Metrics NDJSON should exist with schema-tagged ticks.
    ndjson = (metrics_dir / "metrics.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert ndjson, "metrics.ndjson should not be empty"
    first_tick = json.loads(ndjson[0])
    assert first_tick.get("schema") == "metrics.v1"
