"""Batch benchmark runner for Adaptive Hash Map CLI."""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from adhash import _safe_subprocess
from adhash._safe_subprocess import SubprocessError

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from subprocess import CompletedProcess  # noqa: S404  # nosec B404 - type-only import
else:  # pragma: no cover - used for runtime type hints
    CompletedProcess = Any  # type: ignore[assignment]

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover
    raise ImportError("Python 3.11+ with tomllib support is required") from exc


logger = logging.getLogger(__name__)


@dataclass
class JobSpec:
    name: str
    command: Literal["profile", "run-csv"]
    csv: Path
    mode: str = "adaptive"
    json_summary: Path | None = None
    latency_sample_k: int | None = None
    latency_sample_every: int | None = None
    metrics_out_dir: Path | None = None
    extra_args: list[str] | None = None


@dataclass
class BatchSpec:
    jobs: list[JobSpec]
    report_path: Path
    working_dir: Path
    hashmap_cli: list[str]
    html_report_path: Path | None = None


def load_spec(path: Path) -> BatchSpec:
    data = tomllib.loads(path.read_text())
    batch = data.get("batch")
    if not isinstance(batch, dict):
        raise ValueError("Missing [batch] table in spec")

    report = batch.get("report") or "reports/batch_report.md"
    report_path = (path.parent / report).resolve()
    html_report_value = batch.get("html_report")
    html_report_path = (path.parent / html_report_value).resolve() if html_report_value else None
    hashmap_cli_value = batch.get("hashmap_cli")
    hashmap_cli_parts: list[str]
    if hashmap_cli_value:
        candidate_str = str(hashmap_cli_value)
        candidate_path = (path.parent / candidate_str).resolve()
        if candidate_path.exists():
            hashmap_cli_parts = [str(candidate_path)]
        elif candidate_str.endswith(".py"):
            raise ValueError(f"hashmap_cli.py not found at {candidate_path}")
        else:
            hashmap_cli_parts = shlex.split(candidate_str)
    else:
        hashmap_cli_parts = ["-m", "hashmap_cli"]

    jobs_data = batch.get("jobs")
    if not isinstance(jobs_data, list) or not jobs_data:
        raise ValueError("[batch.jobs] must be a non-empty array")

    jobs: list[JobSpec] = []
    for idx, job_dict in enumerate(jobs_data, 1):
        if not isinstance(job_dict, dict):
            raise ValueError(f"Job #{idx} must be a table")
        name = job_dict.get("name") or f"job-{idx}"
        command = job_dict.get("command")
        if command not in {"profile", "run-csv"}:
            raise ValueError(f"Job '{name}' has unsupported command: {command}")
        csv_value = job_dict.get("csv")
        if not csv_value:
            raise ValueError(f"Job '{name}' missing 'csv' field")
        csv_path = (path.parent / csv_value).resolve()
        mode = job_dict.get("mode", "adaptive")
        json_summary = job_dict.get("json_summary")
        json_path = (path.parent / json_summary).resolve() if json_summary else None
        metrics_out_dir = job_dict.get("metrics_out_dir")
        metrics_path = (path.parent / metrics_out_dir).resolve() if metrics_out_dir else None
        extra_args_raw = job_dict.get("extra_args") or []
        if not isinstance(extra_args_raw, list):
            raise ValueError(f"Job '{name}' extra_args must be a list if provided")
        extra_args = [str(arg) for arg in extra_args_raw]

        command_literal = cast(Literal["profile", "run-csv"], command)

        jobs.append(
            JobSpec(
                name=name,
                command=command_literal,
                csv=csv_path,
                mode=mode,
                json_summary=json_path,
                latency_sample_k=job_dict.get("latency_sample_k"),
                latency_sample_every=job_dict.get("latency_sample_every"),
                metrics_out_dir=metrics_path,
                extra_args=extra_args,
            )
        )

    return BatchSpec(
        jobs=jobs,
        report_path=report_path,
        working_dir=path.parent.resolve(),
        hashmap_cli=hashmap_cli_parts,
        html_report_path=html_report_path,
    )


@dataclass
class JobResult:
    spec: JobSpec
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    summary: dict[str, Any] | None


@dataclass
class _SummaryRow:
    name: str
    ops: float
    duration_seconds: float
    backend: str
    p99_ms: float | None


class BatchRunner:
    _MAX_SUMMARY_ROWS = 500
    _MAX_SNIPPET_CHARS = 4000

    def __init__(self, spec: BatchSpec, python_executable: str | None = None) -> None:
        self.spec = spec
        self.python = self._resolve_python(python_executable)
        self._trusted_executables = {self.python}
        self._project_root = Path.cwd()

    @staticmethod
    def _resolve_python(python_executable: str | None) -> Path:
        candidate = python_executable or sys.executable
        executable = Path(candidate)
        if executable.name == candidate:
            resolved = shutil.which(candidate)
            if resolved is None:
                raise ValueError(f"Unable to locate python executable '{candidate}'")
            executable = Path(resolved)
        return executable.expanduser().resolve()

    def _run_subprocess(self, command: list[str]) -> CompletedProcess[str]:
        if not command:
            raise ValueError("Refusing to execute empty command")
        resolved = Path(command[0])
        if resolved.name == command[0]:
            resolved_lookup = shutil.which(command[0])
            if resolved_lookup is None:
                raise ValueError(f"Executable '{command[0]}' not found on PATH")
            resolved = Path(resolved_lookup)
        resolved = resolved.expanduser().resolve()
        if resolved not in self._trusted_executables:
            raise ValueError(f"Executable '{resolved}' is not trusted for batch execution")

        env = os.environ.copy()
        pythonpath_entries: list[str] = []
        existing_entries: list[Path] = []
        if pythonpath := env.get("PYTHONPATH"):
            for entry in pythonpath.split(os.pathsep):
                if not entry:
                    continue
                entry_path = Path(entry)
                if not entry_path.is_absolute():
                    entry_path = (self._project_root / entry_path).resolve()
                try:
                    resolved = entry_path.resolve()
                except OSError:
                    resolved = entry_path
                existing_entries.append(resolved)
                pythonpath_entries.append(str(resolved))

        def _ensure_path(path: Path) -> None:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved not in existing_entries and path.exists():
                pythonpath_entries.insert(0, str(resolved))
                existing_entries.append(resolved)

        _ensure_path(self._project_root)
        src_dir = self._project_root / "src"
        _ensure_path(src_dir)
        if pythonpath_entries:
            env["PYTHONPATH"] = os.pathsep.join(pythonpath_entries)

        try:
            return _safe_subprocess.safe_run(
                command,
                cwd=str(self.spec.working_dir),
                env=env,
                capture_output=True,
                check=False,
            )
        except SubprocessError as exc:
            raise RuntimeError(str(exc)) from exc

    def run(self) -> list[JobResult]:
        results: list[JobResult] = []
        for job in self.spec.jobs:
            result = self._run_job(job)
            results.append(result)
        self._write_report(results)
        return results

    def _run_job(self, job: JobSpec) -> JobResult:
        command = self._build_command(job)
        start = time.perf_counter()
        try:
            proc = self._run_subprocess(command)
            duration = time.perf_counter() - start
        except OSError as exc:
            duration = time.perf_counter() - start
            logger.error("Failed to launch batch job %s: %s", job.name, exc)
            return JobResult(
                spec=job,
                exit_code=1,
                duration_seconds=duration,
                stdout="",
                stderr=str(exc),
                summary=None,
            )
        except Exception as exc:  # pragma: no cover - defensive guard  # noqa: BLE001
            duration = time.perf_counter() - start
            logger.exception("Unexpected error while running batch job %s", job.name)
            return JobResult(
                spec=job,
                exit_code=1,
                duration_seconds=duration,
                stdout="",
                stderr=str(exc),
                summary=None,
            )

        summary = None
        if proc.returncode == 0 and job.json_summary and job.json_summary.exists():
            try:
                summary = json.loads(job.json_summary.read_text())
            except json.JSONDecodeError as exc:
                logger.warning("Failed to parse summary for job %s: %s", job.name, exc)
                summary = None
        if proc.returncode != 0:
            logger.warning("Batch job %s exited with status %s", job.name, proc.returncode)
        return JobResult(
            spec=job,
            exit_code=proc.returncode,
            duration_seconds=duration,
            stdout=proc.stdout,
            stderr=proc.stderr,
            summary=summary,
        )

    def _build_command(self, job: JobSpec) -> list[str]:
        cli = [str(self.python), *self.spec.hashmap_cli]
        if job.command == "profile":
            cli.extend(
                [
                    "profile",
                    "--csv",
                    str(job.csv),
                ]
            )
        elif job.command == "run-csv":
            cli.extend(
                [
                    "--mode",
                    job.mode,
                    "run-csv",
                    "--csv",
                    str(job.csv),
                ]
            )
            if job.json_summary:
                job.json_summary.parent.mkdir(parents=True, exist_ok=True)
                cli.extend(["--json-summary-out", str(job.json_summary)])
            if job.latency_sample_k is not None:
                cli.extend(["--latency-sample-k", str(job.latency_sample_k)])
            if job.latency_sample_every is not None:
                cli.extend(["--latency-sample-every", str(job.latency_sample_every)])
            if job.metrics_out_dir:
                job.metrics_out_dir.mkdir(parents=True, exist_ok=True)
                cli.extend(["--metrics-out-dir", str(job.metrics_out_dir)])
        if job.extra_args:
            cli.extend(job.extra_args)
        return cli

    def _write_report(self, results: Iterable[JobResult]) -> None:
        lines = [
            "# Adaptive Hash Map Batch Report",
            "",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        metrics_summary: list[_SummaryRow] = []

        rows = [
            "| Job | Command | Status | Duration (s) | Ops/s | Backend |",
            "|---|---|---|---:|---:|---|",
        ]
        for result in results:
            status = "✅" if result.exit_code == 0 else "❌"
            summary = result.summary or {}
            ops_per_second = summary.get("ops_per_second") or summary.get("throughput_ops_per_sec")
            backend_raw = summary.get("final_backend") or summary.get("backend") or "-"
            backend = str(backend_raw)
            latency_packet = (
                summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
            )
            latency_overall = (
                latency_packet.get("overall") if isinstance(latency_packet, dict) else {}
            )
            latency_p99 = latency_overall.get("p99") if isinstance(latency_overall, dict) else None

            safe_name = self._clean_text(result.spec.name, max_chars=120)
            safe_command = self._clean_text(result.spec.command, max_chars=120)
            safe_backend = self._clean_text(backend, max_chars=120)

            ops_fmt = "-"
            if isinstance(ops_per_second, int | float):
                ops_value = float(ops_per_second)
                ops_fmt = f"{ops_value:,.0f}"
                p99_value: float | None
                p99_value = float(latency_p99) if isinstance(latency_p99, int | float) else None
                if len(metrics_summary) < self._MAX_SUMMARY_ROWS:
                    metrics_summary.append(
                        _SummaryRow(
                            name=safe_name,
                            ops=ops_value,
                            duration_seconds=result.duration_seconds,
                            backend=safe_backend,
                            p99_ms=p99_value,
                        )
                    )
            row_line = (
                f"| {safe_name} | {safe_command} | {status} | "
                f"{result.duration_seconds:.2f} | {ops_fmt} | {safe_backend} |"
            )
            rows.append(row_line)

        lines.extend(rows)
        lines.append("")

        if metrics_summary:
            lines.append("## Comparative Summary")
            lines.append("")
            lines.append("| Job | Ops/s | Δ vs. max | p99 latency (ms) |")
            lines.append("|---|---:|---:|---:|")
            best_ops = max(row.ops for row in metrics_summary)
            for row in sorted(metrics_summary, key=lambda data: data.ops, reverse=True):
                delta = 0.0 if best_ops <= 0 else (row.ops - best_ops) / best_ops * 100
                delta_fmt = "0.0%" if abs(delta) < 0.05 else f"{delta:+.1f}%"
                p99_fmt = f"{row.p99_ms:.3f}" if row.p99_ms is not None else "-"
                lines.append(f"| {row.name} | {row.ops:,.0f} | {delta_fmt} | {p99_fmt} |")
            lines.append("")
            lines.append('<div class="ops-chart">')
            for row in sorted(metrics_summary, key=lambda data: data.ops, reverse=True):
                width = 0.0 if best_ops <= 0 else min(100.0, (row.ops / best_ops) * 100)
                bar_html = (
                    '<div class="ops-bar">'
                    f'<span class="ops-label">{row.name}</span>'
                    '<div class="ops-track">'
                    f'<div class="ops-fill" style="width:{width:.1f}%"></div>'
                    "</div>"
                    f'<span class="ops-value">{row.ops:,.0f} ops/s</span>'
                    "</div>"
                )
                lines.append(bar_html)
            lines.append("</div>")
            lines.append("")

        lines.append("## Job Logs")
        for result in results:
            section_title = self._clean_text(result.spec.name, max_chars=120)
            lines.append(f"### {section_title}")
            lines.append("")
            lines.append("```text")
            snippet_raw = result.stdout.strip() or result.stderr.strip()
            snippet = self._clean_text(snippet_raw) if snippet_raw else ""
            lines.append(snippet or "(no output)")
            lines.append("```\n")

        markdown = "\n".join(lines)
        self.spec.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.spec.report_path.write_text(markdown)
        if self.spec.html_report_path is not None:
            self.spec.html_report_path.parent.mkdir(parents=True, exist_ok=True)
            html = self._markdown_to_html(markdown)
            self.spec.html_report_path.write_text(html)

    @staticmethod
    def _clean_text(value: str, *, max_chars: int = 4000) -> str:
        sanitized = []
        for ch in value:
            if ch in {"\n", "\t"} or " " <= ch <= "\ufffd":
                sanitized.append(ch)
        cleaned = "".join(sanitized)
        if len(cleaned) > max_chars:
            return cleaned[:max_chars] + "…"
        return cleaned

    @staticmethod
    def _markdown_to_html(markdown: str) -> str:
        body_lines: list[str] = []
        in_table = False
        header_row = True
        in_code = False

        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            if line.startswith("```"):
                if in_code:
                    body_lines.append("</code></pre>")
                    in_code = False
                else:
                    if in_table:
                        body_lines.append("</table>")
                        in_table = False
                        header_row = True
                    body_lines.append("<pre><code>")
                    in_code = True
                continue

            if in_code:
                body_lines.append(escape(line))
                continue

            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if all(cell.replace("-", "").strip() == "" for cell in cells):
                    continue
                if not in_table:
                    body_lines.append("<table>")
                    in_table = True
                    header_row = True
                tag = "th" if header_row else "td"
                row = "".join(f"<{tag}>{escape(cell)}</{tag}>" for cell in cells)
                body_lines.append(f"<tr>{row}</tr>")
                header_row = False
                continue

            if in_table:
                body_lines.append("</table>")
                in_table = False
                header_row = True

            if line.startswith("# "):
                body_lines.append(f"<h1>{escape(line[2:])}</h1>")
            elif line.startswith("## "):
                body_lines.append(f"<h2>{escape(line[3:])}</h2>")
            elif line.startswith("### "):
                body_lines.append(f"<h3>{escape(line[4:])}</h3>")
            elif line.startswith("<") and line.endswith(">"):
                body_lines.append(line)
            elif line:
                body_lines.append(f"<p>{escape(line)}</p>")

        if in_table:
            body_lines.append("</table>")
        if in_code:
            body_lines.append("</code></pre>")

        html_body = "\n".join(body_lines)
        style_rules = (
            "body{font-family:system-ui,Arial,sans-serif;margin:24px;}"
            "table{border-collapse:collapse;margin:16px 0;}"
            "td,th{border:1px solid #cbd5f5;padding:6px 10px;}"
            "pre{background:#111827;color:#e5e7eb;padding:12px;border-radius:8px;}"
            ".ops-chart{margin:12px 0;display:flex;flex-direction:column;gap:8px;}"
            ".ops-bar{display:flex;align-items:center;gap:12px;font-size:13px;}"
            ".ops-label{flex:0 0 140px;font-weight:600;color:#0f172a;}"
            ".ops-track{flex:1;border:1px solid #cbd5f5;border-radius:6px;height:12px;"
            "overflow:hidden;background:#f2f6ff;}"
            ".ops-fill{height:100%;background:linear-gradient(90deg,#38bdf8,#0f172a);}"
            ".ops-value{width:120px;text-align:right;color:#0f172a;"
            "font-variant-numeric:tabular-nums;}"
        )
        head = (
            "<!DOCTYPE html>"
            "<html><head><meta charset='utf-8'/>"
            "<title>Adaptive Hash Map Batch Report</title>"
            f"<style>{style_rules}</style></head><body>"
        )
        return head + html_body + "</body></html>"


__all__ = [
    "BatchRunner",
    "BatchSpec",
    "JobSpec",
    "load_spec",
]
