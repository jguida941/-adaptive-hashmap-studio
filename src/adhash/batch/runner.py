"""Batch benchmark runner for Adaptive Hash Map CLI."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional

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
    json_summary: Optional[Path] = None
    latency_sample_k: Optional[int] = None
    latency_sample_every: Optional[int] = None
    metrics_out_dir: Optional[Path] = None
    extra_args: List[str] | None = None


@dataclass
class BatchSpec:
    jobs: List[JobSpec]
    report_path: Path
    working_dir: Path
    hashmap_cli: Path
    html_report_path: Optional[Path] = None


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
    if hashmap_cli_value:
        hashmap_cli_path = (path.parent / hashmap_cli_value).resolve()
    else:
        hashmap_cli_path = (path.parent / "hashmap_cli.py").resolve()
    if not hashmap_cli_path.exists():
        raise ValueError(f"hashmap_cli.py not found at {hashmap_cli_path}")

    jobs_data = batch.get("jobs")
    if not isinstance(jobs_data, list) or not jobs_data:
        raise ValueError("[batch.jobs] must be a non-empty array")

    jobs: List[JobSpec] = []
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
        extra_args = job_dict.get("extra_args") or []
        if not isinstance(extra_args, list):
            raise ValueError(f"Job '{name}' extra_args must be a list if provided")

        jobs.append(
            JobSpec(
                name=name,
                command=command,  # type: ignore[arg-type]
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
        hashmap_cli=hashmap_cli_path,
        html_report_path=html_report_path,
    )


@dataclass
class JobResult:
    spec: JobSpec
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    summary: Optional[Dict[str, Any]]


@dataclass
class _SummaryRow:
    name: str
    ops: float
    duration_seconds: float
    backend: str
    p99_ms: Optional[float]


class BatchRunner:
    _MAX_SUMMARY_ROWS = 500
    _MAX_SNIPPET_CHARS = 4000

    def __init__(self, spec: BatchSpec, python_executable: str | None = None) -> None:
        self.spec = spec
        self.python = python_executable or sys.executable

    def run(self) -> List[JobResult]:
        results: List[JobResult] = []
        for job in self.spec.jobs:
            result = self._run_job(job)
            results.append(result)
        self._write_report(results)
        return results

    def _run_job(self, job: JobSpec) -> JobResult:
        command = self._build_command(job)
        start = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.spec.working_dir,
                text=True,
            )
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
        except Exception as exc:  # pragma: no cover - defensive guard
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
            logger.warning(
                "Batch job %s exited with status %s", job.name, proc.returncode
            )
        return JobResult(
            spec=job,
            exit_code=proc.returncode,
            duration_seconds=duration,
            stdout=proc.stdout,
            stderr=proc.stderr,
            summary=summary,
        )

    def _build_command(self, job: JobSpec) -> List[str]:
        cli = [self.python, str(self.spec.hashmap_cli)]
        if job.command == "profile":
            cli.extend([
                "profile",
                "--csv",
                str(job.csv),
            ])
        elif job.command == "run-csv":
            cli.extend([
                "--mode",
                job.mode,
                "run-csv",
                "--csv",
                str(job.csv),
            ])
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
        lines = ["# Adaptive Hash Map Batch Report", "", f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]

        metrics_summary: List[_SummaryRow] = []

        rows = ["| Job | Command | Status | Duration (s) | Ops/s | Backend |", "|---|---|---|---:|---:|---|"]
        for result in results:
            status = "✅" if result.exit_code == 0 else "❌"
            summary = result.summary or {}
            ops_per_second = summary.get("ops_per_second") or summary.get("throughput_ops_per_sec")
            backend_raw = summary.get("final_backend") or summary.get("backend") or "-"
            backend = str(backend_raw)
            latency_packet = summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
            latency_overall = latency_packet.get("overall") if isinstance(latency_packet, dict) else {}
            latency_p99 = latency_overall.get("p99") if isinstance(latency_overall, dict) else None

            safe_name = self._clean_text(result.spec.name, max_chars=120)
            safe_command = self._clean_text(result.spec.command, max_chars=120)
            safe_backend = self._clean_text(backend, max_chars=120)

            ops_fmt = "-"
            if isinstance(ops_per_second, (int, float)):
                ops_value = float(ops_per_second)
                ops_fmt = f"{ops_value:,.0f}"
                p99_value: Optional[float]
                if isinstance(latency_p99, (int, float)):
                    p99_value = float(latency_p99)
                else:
                    p99_value = None
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
            rows.append(
                "| {name} | {command} | {status} | {dur:.2f} | {ops} | {backend} |".format(
                    name=safe_name,
                    command=safe_command,
                    status=status,
                    dur=result.duration_seconds,
                    ops=ops_fmt,
                    backend=safe_backend,
                )
            )

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
                lines.append(
                    "| {name} | {ops:,.0f} | {delta} | {p99} |".format(
                        name=row.name,
                        ops=row.ops,
                        delta=delta_fmt,
                        p99=p99_fmt,
                    )
                )
            lines.append("")
            lines.append('<div class="ops-chart">')
            for row in sorted(metrics_summary, key=lambda data: data.ops, reverse=True):
                width = 0.0 if best_ops <= 0 else min(100.0, (row.ops / best_ops) * 100)
                lines.append(
                    f'<div class="ops-bar"><span class="ops-label">{row.name}</span>'
                    f'<div class="ops-track"><div class="ops-fill" style="width:{width:.1f}%"></div></div>'
                    f'<span class="ops-value">{row.ops:,.0f} ops/s</span></div>'
                )
            lines.append('</div>')
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
        body_lines: List[str] = []
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
            elif line:
                body_lines.append(f"<p>{escape(line)}</p>")

        if in_table:
            body_lines.append("</table>")
        if in_code:
            body_lines.append("</code></pre>")

        html_body = "\n".join(body_lines)
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'/><title>Adaptive Hash Map Batch Report"
            "</title><style>body{font-family:system-ui,Arial,sans-serif;margin:24px;}table{border-collapse:collapse;margin:16px 0;}"
            "td,th{border:1px solid #cbd5f5;padding:6px 10px;}pre{background:#111827;color:#e5e7eb;padding:12px;border-radius:8px;}"
            ".ops-chart{margin:12px 0;display:flex;flex-direction:column;gap:8px;}"
            ".ops-bar{display:flex;align-items:center;gap:12px;font-size:13px;}"
            ".ops-label{flex:0 0 140px;font-weight:600;color:#0f172a;}"
            ".ops-track{flex:1;border:1px solid #cbd5f5;border-radius:6px;height:12px;overflow:hidden;background:#f2f6ff;}"
            ".ops-fill{height:100%;background:linear-gradient(90deg,#38bdf8,#0f172a);}"
            ".ops-value{width:120px;text-align:right;color:#0f172a;font-variant-numeric:tabular-nums;}"
            "</style></head><body>" + html_body + "</body></html>"
        )


__all__ = [
    "BatchRunner",
    "BatchSpec",
    "JobSpec",
    "load_spec",
]
