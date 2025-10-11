from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from adhash._safe_subprocess import safe_run

if TYPE_CHECKING:  # pragma: no cover - typing only
    from subprocess import CompletedProcess
else:  # pragma: no cover - typing fallback
    CompletedProcess = Any

SCRIPT = [sys.executable, "-m", "hashmap_cli.validate_metrics_ndjson"]


def run_validator(path: Path) -> CompletedProcess[str]:
    return safe_run(SCRIPT + [str(path)], check=False)


def write_ndjson(path: Path, *objects: dict[str, object]) -> None:
    payload = "\n".join(json.dumps(obj) for obj in objects)
    path.write_text(payload + "\n", encoding="utf-8")


def make_base_metrics() -> dict[str, object]:
    return {
        "schema": "metrics.v1",
        "t": 0.0,
        "backend": "robinhood",
        "ops": 1,
        "load_factor": 0.52,
        "latency_ms": {"overall": {"p50": 1.0, "p90": 1.5, "p99": 2.0}},
    }


def test_validator_accepts_valid_metrics(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.ndjson"
    write_ndjson(metrics_path, make_base_metrics())
    result = run_validator(metrics_path)
    assert result.returncode == 0
    assert "all lines valid" in result.stdout
    assert result.stderr.strip() == ""


def test_validator_rejects_schema_violation(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.ndjson"
    bad = make_base_metrics()
    bad.pop("schema")
    write_ndjson(metrics_path, bad)
    result = run_validator(metrics_path)
    assert result.returncode == 1
    assert "invalid line" in result.stderr
    assert "schema" in result.stderr.lower()
    summary = (result.stdout + result.stderr).lower()
    assert "1 invalid" in summary


def test_validator_rejects_non_monotonic_latency(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.ndjson"
    bad = make_base_metrics()
    latency_packet = cast(dict[str, dict[str, float]], bad["latency_ms"])
    overall_latency = latency_packet["overall"]
    overall_latency["p90"] = 0.5
    write_ndjson(metrics_path, bad)
    result = run_validator(metrics_path)
    assert result.returncode == 1
    assert "non-monotonic" in result.stderr
    summary = (result.stdout + result.stderr).lower()
    assert "1 invalid" in summary
