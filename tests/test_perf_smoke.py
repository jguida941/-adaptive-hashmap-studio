import contextlib
import io
import json
import os
import subprocess
from pathlib import Path

import pytest

import hashmap_cli
from adhash.metrics import TICK_SCHEMA

if os.getenv("MUTATION_TESTS") == "1":
    pytestmark = pytest.mark.skip(reason="perf smoke tests disabled during mutation runs")


def run(argv: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    prev_dir = Path.cwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = hashmap_cli.main(argv)
            except SystemExit as exc:
                if isinstance(exc.code, int):
                    code = exc.code
                elif exc.code is None:
                    code = 0
                else:
                    code = 1
    finally:
        hashmap_cli.OUTPUT_JSON = False
        if cwd is not None:
            os.chdir(prev_dir)
    stdout_text = stdout.getvalue()
    stderr_text = stderr.getvalue()
    if code != 0:
        raise subprocess.CalledProcessError(
            code, ["hashmap_cli"] + argv, output=stdout_text, stderr=stderr_text
        )
    return subprocess.CompletedProcess(["hashmap_cli"] + argv, code, stdout_text, stderr_text)


def test_run_csv_perf_smoke(tmp_path: Path) -> None:
    workload = tmp_path / "smoke.csv"
    summary_path = tmp_path / "summary.json"
    metrics_dir = tmp_path / "metrics"

    run(
        [
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
        [
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

    assert completed.returncode == 0
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data["total_ops"] == 200
    assert data["ops_per_second"] is None or data["ops_per_second"] > 0
    assert data["final_backend"] in {"chaining", "robinhood", "memory-tight", "adaptive"}

    ndjson = (metrics_dir / "metrics.ndjson").read_text(encoding="utf-8").strip().splitlines()
    assert ndjson, "metrics.ndjson should not be empty"
    first_tick = json.loads(ndjson[0])
    assert first_tick.get("schema") == TICK_SCHEMA


def test_run_csv_emits_histograms_without_summary(tmp_path: Path) -> None:
    workload = tmp_path / "histogram.csv"
    metrics_dir = tmp_path / "metrics"

    run(
        [
            "generate-csv",
            "--outfile",
            str(workload),
            "--ops",
            "400",
            "--read-ratio",
            "0.5",
            "--key-skew",
            "0.4",
            "--key-space",
            "256",
            "--seed",
            "99",
        ]
    )

    completed = run(
        [
            "--mode",
            "fast-lookup",
            "run-csv",
            "--csv",
            str(workload),
            "--metrics-out-dir",
            str(metrics_dir),
            "--metrics-max-ticks",
            "32",
            "--latency-sample-k",
            "128",
            "--latency-sample-every",
            "8",
        ]
    )
    assert completed.returncode == 0

    ndjson_path = metrics_dir / "metrics.ndjson"
    ticks = [
        json.loads(line)
        for line in ndjson_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert ticks, "expected metrics ticks"

    hist_tick = next((tick for tick in reversed(ticks) if tick.get("latency_hist_ms")), None)
    assert hist_tick is not None, "latency histogram never emitted"
    overall_hist = hist_tick["latency_hist_ms"].get("overall", [])
    assert overall_hist, "overall latency histogram is empty"

    probe_hist = hist_tick.get("probe_hist", [])
    assert probe_hist, "probe histogram should not be empty for fast-lookup mode"
