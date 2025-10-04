"""Workload DNA analyzer.

Reads workload CSV files and extracts statistical fingerprints (ratios, skew,
value/key characteristics). Designed to run quickly on multi-million row CSVs
without loading everything into memory.
"""

from __future__ import annotations

import csv
import math
from collections import Counter, deque
from dataclasses import dataclass
from hashlib import blake2b
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from adhash.contracts.error import BadInputError

_CSV_HINT = "See docs/workload_schema.md"
_KNOWN_OPS = {"put", "get", "del"}
_DEFAULT_TOP_KEYS = 10
_MAX_TRACKED_KEYS = 200_000
_HASH_BUCKET_BITS = 12  # 4096 buckets keeps collision check cheap

__all__ = [
    "WorkloadDNAResult",
    "analyze_workload_csv",
    "format_workload_dna",
]


@dataclass(slots=True)
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min: Optional[float] = None
    max: Optional[float] = None

    def add(self, value: float) -> None:
        if self.count == 0:
            self.min = self.max = value
        else:
            if self.min is not None and value < self.min:
                self.min = value
            if self.max is not None and value > self.max:
                self.max = value
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2

    def to_dict(self) -> Mapping[str, float]:
        if self.count == 0:
            return {
                "count": 0,
                "min": 0.0,
                "max": 0.0,
                "mean": 0.0,
                "stdev": 0.0,
            }
        variance = self.m2 / self.count if self.count > 1 else 0.0
        return {
            "count": float(self.count),
            "min": float(self.min if self.min is not None else 0.0),
            "max": float(self.max if self.max is not None else 0.0),
            "mean": float(self.mean),
            "stdev": math.sqrt(variance),
        }


@dataclass(frozen=True)
class WorkloadDNAResult:
    schema: str
    csv_path: str
    file_size_bytes: Optional[int]
    total_rows: int
    op_counts: Mapping[str, int]
    op_mix: Mapping[str, float]
    mutation_fraction: float
    unique_keys_estimated: int
    key_space_depth: float
    key_length_stats: Mapping[str, float]
    value_size_stats: Mapping[str, float]
    key_entropy_bits: float
    key_entropy_normalised: float
    hot_keys: Tuple[Mapping[str, float], ...]
    coverage_targets: Mapping[str, int]
    numeric_key_fraction: float
    sequential_numeric_step_fraction: float
    adjacent_duplicate_fraction: float
    hash_collision_hotspots: Mapping[str, int]
    bucket_counts: Tuple[int, ...]
    bucket_percentiles: Mapping[str, float]
    collision_depth_histogram: Mapping[int, int]
    non_empty_buckets: int
    max_bucket_depth: int

    def to_dict(self) -> Mapping[str, object]:
        return {
            "schema": self.schema,
            "csv_path": self.csv_path,
            "file_size_bytes": self.file_size_bytes,
            "total_rows": self.total_rows,
            "op_counts": dict(self.op_counts),
            "op_mix": dict(self.op_mix),
            "mutation_fraction": self.mutation_fraction,
            "unique_keys_estimated": self.unique_keys_estimated,
            "key_space_depth": self.key_space_depth,
            "key_length_stats": dict(self.key_length_stats),
            "value_size_stats": dict(self.value_size_stats),
            "key_entropy_bits": self.key_entropy_bits,
            "key_entropy_normalised": self.key_entropy_normalised,
            "hot_keys": tuple(dict(entry) for entry in self.hot_keys),
            "coverage_targets": dict(self.coverage_targets),
            "numeric_key_fraction": self.numeric_key_fraction,
            "sequential_numeric_step_fraction": self.sequential_numeric_step_fraction,
            "adjacent_duplicate_fraction": self.adjacent_duplicate_fraction,
            "hash_collision_hotspots": dict(self.hash_collision_hotspots),
            "bucket_counts": list(self.bucket_counts),
            "bucket_percentiles": dict(self.bucket_percentiles),
            "collision_depth_histogram": dict(self.collision_depth_histogram),
            "non_empty_buckets": self.non_empty_buckets,
            "max_bucket_depth": self.max_bucket_depth,
        }


def analyze_workload_csv(
    path: str | Path,
    *,
    top_keys: int = _DEFAULT_TOP_KEYS,
    max_tracked_keys: int = _MAX_TRACKED_KEYS,
) -> WorkloadDNAResult:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    file_size: Optional[int]
    try:
        file_size = csv_path.stat().st_size
    except OSError:
        file_size = None

    op_counts: Counter[str] = Counter()
    key_lengths = RunningStats()
    value_sizes = RunningStats()
    key_counter: MutableMapping[str, int] = Counter()
    hash_buckets: MutableMapping[int, int] = Counter()
    unique_hashes: set[int] = set()
    unique_keys: int = 0

    prev_key: Optional[str] = None
    dup_runs = 0

    numeric_keys = 0
    numeric_pair_total = 0
    numeric_step_matches = 0
    prev_numeric_value: Optional[int] = None

    reader_line = 0
    with csv_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        header = {fn.strip() for fn in (reader.fieldnames or [])}
        missing = {"op", "key", "value"} - header
        if missing:
            raise BadInputError(f"Missing header columns: {', '.join(sorted(missing))}", hint=_CSV_HINT)
        unexpected = header - {"op", "key", "value"}
        if unexpected:
            raise BadInputError(
                f"Unexpected column(s) in header: {', '.join(sorted(unexpected))}",
                hint=_CSV_HINT,
            )

        for row in reader:
            reader_line = reader.line_num
            op_raw = (row.get("op") or "").strip().lower()
            if op_raw not in _KNOWN_OPS:
                raise BadInputError(f"Unknown op '{op_raw}' at line {reader_line}", hint=_CSV_HINT)
            key = (row.get("key") or "").strip()
            if not key:
                raise BadInputError(f"Missing key at line {reader_line}", hint=_CSV_HINT)
            value = row.get("value") or ""

            op_counts[op_raw] += 1

            key_len = len(key)
            key_lengths.add(float(key_len))

            if op_raw == "put":
                value_sizes.add(float(len(value)))

            unique_marker = _stable_hash(key)
            if unique_marker not in unique_hashes:
                unique_hashes.add(unique_marker)
                unique_keys += 1
                low_bucket = unique_marker & ((1 << _HASH_BUCKET_BITS) - 1)
                hash_buckets[low_bucket] += 1

            key_counter[key] += 1
            if len(key_counter) > max_tracked_keys:
                _decay_counter(key_counter)

            if prev_key == key:
                dup_runs += 1
            prev_key = key

            numeric_value = _extract_numeric_token(key)
            if numeric_value is not None:
                numeric_keys += 1
                if prev_numeric_value is not None:
                    numeric_pair_total += 1
                    if numeric_value == prev_numeric_value + 1:
                        numeric_step_matches += 1
                prev_numeric_value = numeric_value
            else:
                prev_numeric_value = None

    total_rows = sum(op_counts.values())
    if total_rows == 0:
        raise BadInputError("CSV contains no data rows", hint=_CSV_HINT)

    op_mix = {op: op_counts[op] / total_rows for op in _KNOWN_OPS}
    mutation_fraction = (op_counts["put"] + op_counts["del"]) / total_rows
    key_space_depth = total_rows / unique_keys if unique_keys else 0.0
    numeric_fraction = numeric_keys / total_rows
    sequential_fraction = (
        numeric_step_matches / numeric_pair_total if numeric_pair_total else 0.0
    )
    duplicate_fraction = dup_runs / total_rows

    entropy_bits = _shannon_entropy(key_counter.values())
    max_entropy = math.log2(unique_keys) if unique_keys > 1 else 0.0
    entropy_normalised = entropy_bits / max_entropy if max_entropy > 0 else 0.0

    hot_keys = _format_hot_keys(key_counter, top_keys, total_rows)
    coverage = _coverage_targets(key_counter, total_rows)
    bucket_counts = _materialise_buckets(hash_buckets)
    non_empty_buckets = sum(1 for count in bucket_counts if count > 0)
    max_bucket_depth = max(bucket_counts) if bucket_counts else 0
    depth_histogram = _collision_depth_histogram(bucket_counts)
    bucket_percentiles = _bucket_percentiles(bucket_counts)
    collision_hotspots = {
        f"0x{bucket:03x}": count
        for bucket, count in sorted(hash_buckets.items(), key=lambda item: item[1], reverse=True)
        if count > 1
    }

    result = WorkloadDNAResult(
        schema="workload_dna.v1",
        csv_path=str(csv_path),
        file_size_bytes=file_size,
        total_rows=total_rows,
        op_counts={op: op_counts.get(op, 0) for op in _KNOWN_OPS},
        op_mix=op_mix,
        mutation_fraction=mutation_fraction,
        unique_keys_estimated=unique_keys,
        key_space_depth=key_space_depth,
        key_length_stats=key_lengths.to_dict(),
        value_size_stats=value_sizes.to_dict(),
        key_entropy_bits=entropy_bits,
        key_entropy_normalised=entropy_normalised,
        hot_keys=tuple(hot_keys),
        coverage_targets=coverage,
        numeric_key_fraction=numeric_fraction,
        sequential_numeric_step_fraction=sequential_fraction,
        adjacent_duplicate_fraction=duplicate_fraction,
        hash_collision_hotspots=collision_hotspots,
        bucket_counts=tuple(bucket_counts),
        bucket_percentiles=bucket_percentiles,
        collision_depth_histogram=depth_histogram,
        non_empty_buckets=non_empty_buckets,
        max_bucket_depth=max_bucket_depth,
    )
    return result


def _decay_counter(counter: MutableMapping[str, int]) -> None:
    for key in list(counter.keys()):
        new_value = counter[key] - 1
        if new_value <= 0:
            del counter[key]
        else:
            counter[key] = new_value


def _stable_hash(value: str) -> int:
    digest = blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _extract_numeric_token(key: str) -> Optional[int]:
    if not key:
        return None
    if key.isdigit() or (key[0] == "-" and key[1:].isdigit()):
        try:
            return int(key)
        except ValueError:
            return None
    suffix: Deque[str] = deque()
    for ch in reversed(key):
        if ch.isdigit():
            suffix.appendleft(ch)
        else:
            break
    if suffix:
        try:
            return int("".join(suffix))
        except ValueError:
            return None
    return None


def _format_hot_keys(counter: Mapping[str, int], limit: int, total: int) -> List[Mapping[str, float]]:
    if not counter:
        return []
    most_common = Counter(counter).most_common(limit)
    formatted: List[Mapping[str, float]] = []
    for key, count in most_common:
        share = count / total if total else 0.0
        formatted.append({
            "key": key,
            "count": float(count),
            "share": share,
        })
    return formatted


def _coverage_targets(counter: Mapping[str, int], total: int) -> Mapping[str, int]:
    if not counter or total == 0:
        return {"p50": 0, "p80": 0, "p95": 0}
    sorted_counts = sorted(counter.values(), reverse=True)
    targets = {0.5: "p50", 0.8: "p80", 0.95: "p95"}
    result: Dict[str, int] = {label: 0 for label in targets.values()}
    cumulative = 0
    idx = 0
    for count in sorted_counts:
        idx += 1
        cumulative += count
        coverage = cumulative / total
        for threshold, label in targets.items():
            if result[label] == 0 and coverage >= threshold:
                result[label] = idx
    for label in result:
        if result[label] == 0:
            result[label] = len(sorted_counts)
    return result


def _shannon_entropy(values: Iterable[int]) -> float:
    total = 0
    accum: List[int] = []
    for value in values:
        if value <= 0:
            continue
        accum.append(value)
        total += value
    if total == 0:
        return 0.0
    entropy = 0.0
    for value in accum:
        probability = value / total
        entropy -= probability * math.log2(probability)
    return entropy


def format_workload_dna(result: WorkloadDNAResult) -> str:
    lines: List[str] = []
    size_hint = (
        f"{result.file_size_bytes:,} bytes" if result.file_size_bytes is not None else "unknown size"
    )
    lines.append(f"Workload DNA for {Path(result.csv_path).name} — {result.total_rows:,} rows ({size_hint})")
    mix_parts = [f"{op}: {result.op_mix.get(op, 0.0):.1%}" for op in sorted(result.op_mix.keys())]
    lines.append("Mix: " + ", ".join(mix_parts))
    lines.append(
        f"Unique keys ≈ {result.unique_keys_estimated:,} (avg touches {result.key_space_depth:.2f})"
    )
    lines.append(f"Mutating ops: {result.mutation_fraction:.1%}; adj dupes: {result.adjacent_duplicate_fraction:.1%}")
    lines.append(
        "Key length → "
        f"mean {result.key_length_stats.get('mean', 0.0):.2f}, "
        f"min {result.key_length_stats.get('min', 0.0):.0f}, "
        f"max {result.key_length_stats.get('max', 0.0):.0f}"
    )
    if result.value_size_stats.get("count", 0.0):
        lines.append(
            "Value size → "
            f"mean {result.value_size_stats.get('mean', 0.0):.1f}B, "
            f"max {result.value_size_stats.get('max', 0.0):.0f}B"
        )
    lines.append(
        f"Numeric keys: {result.numeric_key_fraction:.1%} (sequential step {result.sequential_numeric_step_fraction:.1%})"
    )
    lines.append(
        f"Entropy: {result.key_entropy_bits:.2f} bits ({result.key_entropy_normalised:.1%} of max)"
    )
    coverage = result.coverage_targets
    lines.append(
        "Coverage: "
        f"p50→{coverage.get('p50', 0)}, p80→{coverage.get('p80', 0)}, p95→{coverage.get('p95', 0)} keys"
    )
    if result.hot_keys:
        lines.append("Hot keys:")
        for entry in result.hot_keys:
            key = entry.get("key", "?")
            count = entry.get("count", 0.0)
            share = entry.get("share", 0.0)
            lines.append(f"  • {key}: {int(count):,} ({_format_share(share)})")
    if result.hash_collision_hotspots:
        lines.append("Hash collision hotspots:")
        for bucket, count in list(result.hash_collision_hotspots.items())[:5]:
            lines.append(f"  • bucket {bucket} → {count} keys")
    return "\n".join(lines)


def _materialise_buckets(hash_buckets: Mapping[int, int]) -> List[int]:
    bucket_count = 1 << _HASH_BUCKET_BITS
    counts = [0] * bucket_count
    for bucket, count in hash_buckets.items():
        if 0 <= bucket < bucket_count:
            counts[bucket] = count
    return counts


def _collision_depth_histogram(bucket_counts: Iterable[int]) -> Mapping[int, int]:
    histogram: Dict[int, int] = {}
    for count in bucket_counts:
        histogram[count] = histogram.get(count, 0) + 1
    return histogram


def _bucket_percentiles(bucket_counts: Iterable[int]) -> Mapping[str, float]:
    data = [float(value) for value in bucket_counts]
    non_zero = [value for value in data if value > 0.0]
    target = non_zero if non_zero else data
    if not target:
        return {key: 0.0 for key in ("p50", "p75", "p90", "p95", "p99")}
    sorted_vals = sorted(target)
    return {
        "p50": _percentile(sorted_vals, 0.5),
        "p75": _percentile(sorted_vals, 0.75),
        "p90": _percentile(sorted_vals, 0.90),
        "p95": _percentile(sorted_vals, 0.95),
        "p99": _percentile(sorted_vals, 0.99),
    }


def _percentile(sorted_values: List[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = q * (len(sorted_values) - 1)
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = position - lower_index
    return lower_value + (upper_value - lower_value) * weight


def _format_share(share: float) -> str:
    if share <= 0.0:
        return "0"
    if share >= 0.001:
        return f"{share * 100:.2f}%"
    return f"{share * 10000:.1f} bp"
