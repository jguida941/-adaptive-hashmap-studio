from __future__ import annotations

from pathlib import Path

import pytest

from adhash.contracts.error import BadInputError
from adhash.workloads import analyze_workload_csv


def _write_csv(path: Path, rows: list[tuple[str, str, str]]) -> None:
    lines = ["op,key,value"]
    for op, key, value in rows:
        lines.append(f"{op},{key},{value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_analyze_workload_basic(tmp_path: Path) -> None:
    csv_path = tmp_path / "basic.csv"
    _write_csv(
        csv_path,
        [
            ("put", "alpha", "value"),
            ("get", "alpha", ""),
            ("put", "beta", "longer"),
            ("del", "alpha", ""),
            ("get", "beta", ""),
            ("put", "alpha", "123"),
        ],
    )

    result = analyze_workload_csv(csv_path)

    assert result.total_rows == 6
    assert result.op_counts["put"] == 3
    assert pytest.approx(result.op_mix["put"], rel=1e-6) == 0.5
    assert result.unique_keys_estimated == 2
    assert result.key_space_depth == pytest.approx(3.0)
    assert result.hot_keys[0]["key"] == "alpha"
    assert result.coverage_targets["p50"] == 1
    assert result.mutation_fraction > 0.0
    assert result.numeric_key_fraction == 0.0
    assert result.hash_collision_hotspots == {}
    assert len(result.bucket_counts) == 1 << 12
    assert result.non_empty_buckets == 2
    assert result.max_bucket_depth >= 1
    assert result.bucket_percentiles["p95"] >= 1.0


def test_analyze_workload_numeric_sequences(tmp_path: Path) -> None:
    csv_path = tmp_path / "numeric.csv"
    rows = []
    for idx in range(1, 6):
        rows.append(("put", f"key{idx}", "v"))
        rows.append(("get", f"key{idx}", ""))
    _write_csv(csv_path, rows)

    result = analyze_workload_csv(csv_path)

    assert result.numeric_key_fraction == pytest.approx(1.0)
    assert result.sequential_numeric_step_fraction > 0.0
    assert result.adjacent_duplicate_fraction > 0.0
    assert result.bucket_percentiles["p99"] >= 1.0


def test_analyze_missing_header(tmp_path: Path) -> None:
    csv_path = tmp_path / "broken.csv"
    csv_path.write_text("op,key\nput,a\n", encoding="utf-8")

    with pytest.raises(BadInputError):
        analyze_workload_csv(csv_path)
