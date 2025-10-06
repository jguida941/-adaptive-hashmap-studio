"""Benchmark suite management pane."""

from __future__ import annotations

import math
import time
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from concurrent.futures import ThreadPoolExecutor, Future

from adhash.batch.runner import BatchSpec, JobSpec, load_spec
from adhash.contracts.error import BadInputError
from adhash.workloads import WorkloadDNAResult, analyze_workload_csv, format_workload_dna

from .common import (
    QColor,
    QCheckBox,
    QComboBox,
    QCursor,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QToolTip,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
    pg,
    np,
    pyqtSignal,
    QObject,
)


T = TypeVar("T")


if QObject is not None and pyqtSignal is not None:  # type: ignore[truthy-bool]
    class _MainThreadInvoker(QObject):  # type: ignore[misc]
        """Queue callbacks onto the Qt main thread."""

        call = pyqtSignal(object)  # type: ignore[call-arg]

        def __init__(self, parent: Optional[QObject] = None) -> None:  # type: ignore[override]
            super().__init__(parent)
            self.call.connect(self._dispatch)  # type: ignore[attr-defined]

        def submit(self, func: Callable[[], None]) -> None:
            self.call.emit(func)  # type: ignore[attr-defined]

        def _dispatch(self, payload: object) -> None:
            if callable(payload):
                payload()


else:  # pragma: no cover - PyQt6 missing in test envs
    class _MainThreadInvoker:  # type: ignore[too-few-public-methods]
        def __init__(self, parent: Optional[object] = None) -> None:
            self._parent = parent

        def submit(self, func: Callable[[], None]) -> None:
            func()


class BenchmarkSuitePane(QWidget):  # type: ignore[misc]
    """Mission Control pane for managing batch benchmark suites."""

    _HISTORY_LIMIT = 20

    if pyqtSignal is not None:  # type: ignore[truthy-bool]
        analysisCompleted = pyqtSignal(object, object, object)  # type: ignore[call-arg]
    else:  # pragma: no cover - signals only exist when Qt is available
        analysisCompleted = None  # type: ignore[assignment]

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "suite")
        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Benchmark Suites")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        path_row = QHBoxLayout()  # type: ignore[call-arg]
        path_label = QLabel("Spec path:")  # type: ignore[call-arg]
        self.spec_edit = QLineEdit("docs/examples/batch_baseline.toml")  # type: ignore[call-arg]
        self.spec_edit.setObjectName("suiteSpecEdit")
        self.load_button = QPushButton("Load spec")  # type: ignore[call-arg]
        self.load_button.setObjectName("suiteLoadButton")
        self.discover_button = QPushButton("Discover")  # type: ignore[call-arg]
        self.discover_button.setObjectName("suiteDiscoverButton")
        self.cancel_discovery_button = QPushButton("Cancel")  # type: ignore[call-arg]
        self.cancel_discovery_button.setObjectName("suiteCancelDiscovery")
        self.cancel_discovery_button.setEnabled(False)
        path_row.addWidget(path_label)
        path_row.addWidget(self.spec_edit, 1)
        path_row.addWidget(self.load_button)
        path_row.addWidget(self.discover_button)
        path_row.addWidget(self.cancel_discovery_button)
        layout.addLayout(path_row)

        self.discovery_progress = QProgressBar() if QProgressBar is not None else None  # type: ignore[call-arg]
        if self.discovery_progress is not None:
            self.discovery_progress.setRange(0, 0)
            self.discovery_progress.setObjectName("suiteDiscoveryProgress")
            self.discovery_progress.hide()
            layout.addWidget(self.discovery_progress)

        self.spec_selector = QComboBox() if QComboBox is not None else None  # type: ignore[call-arg]
        if self.spec_selector is not None:
            self.spec_selector.setObjectName("suiteSpecSelector")  # type: ignore[attr-defined]
            self.spec_selector.currentIndexChanged.connect(self._on_spec_selected)  # type: ignore[attr-defined]
            layout.addWidget(self.spec_selector)

        self.status_label = QLabel("Idle")  # type: ignore[call-arg]
        self.status_label.setObjectName("suiteStatusLabel")
        self.status_label.setProperty("state", "idle")
        layout.addWidget(self.status_label)

        self.summary_label = QLabel("No spec loaded.")  # type: ignore[call-arg]
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("suiteSummaryLabel")
        layout.addWidget(self.summary_label)

        self.summary_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.summary_view.setObjectName("suiteSummaryView")
        self.summary_view.setReadOnly(True)
        self.summary_view.setMaximumBlockCount(400)
        layout.addWidget(self.summary_view)

        job_row = QHBoxLayout()  # type: ignore[call-arg]
        job_label = QLabel("Job:")  # type: ignore[call-arg]
        self.job_selector = QComboBox() if QComboBox is not None else None  # type: ignore[call-arg]
        self.analyze_button = QPushButton("Analyze workload")  # type: ignore[call-arg]
        job_row.addWidget(job_label)
        if self.job_selector is not None:
            self.job_selector.setObjectName("suiteJobSelector")  # type: ignore[attr-defined]
            job_row.addWidget(self.job_selector, 1)
        else:
            job_row.addStretch()  # type: ignore[attr-defined]
        job_row.addWidget(self.analyze_button)
        layout.addLayout(job_row)

        control_row = QHBoxLayout()  # type: ignore[call-arg]
        self.run_button = QPushButton("Run suite")  # type: ignore[call-arg]
        self.run_button.setObjectName("suiteRunButton")
        self.stop_button = QPushButton("Stop")  # type: ignore[call-arg]
        self.stop_button.setObjectName("suiteStopButton")
        self.stop_button.setEnabled(False)
        control_row.addWidget(self.run_button)
        control_row.addWidget(self.stop_button)
        control_row.addStretch()  # type: ignore[attr-defined]
        self.timer_label = QLabel("Elapsed: 0.0s")  # type: ignore[call-arg]
        self.timer_label.setObjectName("suiteTimerLabel")
        control_row.addWidget(self.timer_label)
        layout.addLayout(control_row)

        log_heading = QLabel("Run output")  # type: ignore[call-arg]
        log_heading.setObjectName("paneHeading")
        layout.addWidget(log_heading)

        self.log_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.log_view.setObjectName("suiteLogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        layout.addWidget(self.log_view)

        analysis_heading = QLabel("Workload DNA")  # type: ignore[call-arg]
        analysis_heading.setObjectName("paneHeading")
        layout.addWidget(analysis_heading)

        self.analysis_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.analysis_view.setObjectName("suiteAnalysisView")
        self.analysis_view.setReadOnly(True)
        self.analysis_view.setMaximumBlockCount(400)
        self.analysis_view.setPlaceholderText("Select a job and run analysis to view workload DNA.")  # type: ignore[attr-defined]
        layout.addWidget(self.analysis_view)

        history_heading = QLabel("Recent runs")  # type: ignore[call-arg]
        history_heading.setObjectName("paneHeading")
        layout.addWidget(history_heading)

        self.history_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.history_view.setObjectName("suiteHistoryView")
        self.history_view.setReadOnly(True)
        self.history_view.setMaximumBlockCount(200)
        self.history_view.setPlaceholderText("Runs will appear here after execution.")  # type: ignore[attr-defined]
        layout.addWidget(self.history_view)

        self._timer = QTimer(self) if QTimer is not None else None
        if self._timer is not None:
            self._timer.setInterval(200)
            self._timer.timeout.connect(self._on_timer_tick)  # type: ignore[attr-defined]
        self._start_time: Optional[float] = None

        self._history: List[str] = []
        self._current_spec: Optional[BatchSpec] = None
        self._current_spec_path: Optional[Path] = None
        self._active_spec: Optional[BatchSpec] = None
        self._active_spec_path: Optional[Path] = None
        self._job_lookup: Dict[str, JobSpec] = {}
        self._job_order: List[JobSpec] = []
        self._analysis_callbacks: List[Callable[[WorkloadDNAResult, JobSpec, Path], None]] = []
        self._discovering_specs = False
        self._loading_spec = False
        self._discovery_token = 0
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="suite-pane")
        self._active_future: Optional[Future[Any]] = None
        self._main_thread = _MainThreadInvoker(self if Qt is not None else None)

        self.load_button.clicked.connect(self._on_load_clicked)  # type: ignore[attr-defined]
        self.discover_button.clicked.connect(lambda: self.refresh_specs(select_first=True))  # type: ignore[attr-defined]
        self.cancel_discovery_button.clicked.connect(self._cancel_discovery)  # type: ignore[attr-defined]
        self.analyze_button.clicked.connect(self._on_analyze_clicked)  # type: ignore[attr-defined]

        self.refresh_specs(select_first=True)

    def set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self._repolish(self.status_label)

    def _repolish(self, widget: QWidget) -> None:
        if Qt is None:
            return
        style = widget.style()
        if style is None:  # pragma: no cover - headless fallback
            return
        style.unpolish(widget)  # type: ignore[attr-defined]
        style.polish(widget)  # type: ignore[attr-defined]

    def refresh_specs(self, *, select_first: bool) -> None:
        """Discover example suite specs without blocking the UI."""

        if self.spec_selector is None or self._discovering_specs:
            return

        self._cancel_active_future()
        self._discovering_specs = True
        self._discovery_token += 1
        token = self._discovery_token
        self.set_status("Scanning for suite specs…", "running")
        self.discover_button.setEnabled(False)
        self.cancel_discovery_button.setEnabled(True)
        if self.discovery_progress is not None:
            self.discovery_progress.show()
        if not self._loading_spec:
            self.load_button.setEnabled(False)

        def on_complete(specs: List[Path]) -> None:
            if token != self._discovery_token:
                return
            self._finalize_discovery(cancelled=False)
            self._populate_spec_selector(specs, select_first)

        def on_error(exc: Exception) -> None:
            if token != self._discovery_token:
                return
            self._finalize_discovery(cancelled=False)
            self.set_status(f"Discovery error: {exc}", "error")

        self._run_background(self._discover_specs, on_complete, on_error)

    def _discover_specs(self) -> List[Path]:
        roots = [
            Path.cwd() / "docs" / "examples",
            Path.cwd() / "docs" / "benchmarks",
        ]
        found: List[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if not root.exists():
                continue
            for candidate in sorted(root.glob("batch*.toml")):
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                try:
                    load_spec(resolved)
                except Exception:
                    continue
                seen.add(resolved)
                found.append(resolved)
        return found

    def _finalize_discovery(self, *, cancelled: bool) -> None:
        self._discovering_specs = False
        self.discover_button.setEnabled(True)
        self.cancel_discovery_button.setEnabled(False)
        if self.discovery_progress is not None:
            self.discovery_progress.hide()
        if not self._loading_spec:
            self.load_button.setEnabled(True)
        if cancelled:
            self.set_status("Discovery cancelled.", "idle")
        self._active_future = None

    def _cancel_discovery(self) -> None:
        if not self._discovering_specs:
            return
        self._discovery_token += 1
        self._cancel_active_future()
        self._finalize_discovery(cancelled=True)

    def _run_background(
        self,
        work: Callable[[], T],
        on_success: Callable[[T], None],
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        future = self._executor.submit(work)
        self._active_future = future

        def handle_future(fut: Future[Any]) -> None:
            self._active_future = None
            try:
                result = fut.result()
            except Exception as exc:
                if on_error is not None:
                    self._invoke_main_thread(partial(on_error, exc))
            else:
                self._invoke_main_thread(lambda: on_success(result))

        future.add_done_callback(handle_future)

    def _invoke_main_thread(self, func: Callable[[], None]) -> None:
        if self._main_thread is not None:
            self._main_thread.submit(func)
        else:
            func()

    def _cancel_active_future(self) -> None:
        future = self._active_future
        if future is not None and not future.done():
            future.cancel()
        self._active_future = None

    def _format_spec_label(self, path: Path) -> str:
        try:
            resolved = path.resolve()
            cwd = Path.cwd().resolve()
            label = str(resolved.relative_to(cwd))
        except Exception:
            label = str(path)
        return label

    def _on_spec_selected(self, index: int) -> None:
        if self.spec_selector is None:
            return
        data = self.spec_selector.itemData(index)  # type: ignore[attr-defined]
        if isinstance(data, str):
            self.spec_edit.setText(data)

    def _on_load_clicked(self) -> None:
        if self._loading_spec:
            return
        path = self.get_spec_path()
        if path is None:
            self.set_status("Enter a spec path to load.", "error")
            return
        self._loading_spec = True
        self.load_button.setEnabled(False)
        self.set_status(f"Loading {path}…", "running")

        def load_work() -> BatchSpec:
            return load_spec(path)

        def on_loaded(spec: BatchSpec) -> None:
            self._loading_spec = False
            self.load_button.setEnabled(True)
            self._current_spec = spec
            self._current_spec_path = path
            self._ensure_selector_entry(path)
            self._render_spec(spec, path)
            self.set_status(f"Loaded {path}", "idle")

        def on_error(exc: Exception) -> None:
            self._loading_spec = False
            self.load_button.setEnabled(True)
            if isinstance(exc, FileNotFoundError):
                self.set_status(f"Spec not found: {path}", "error")
            else:
                self.set_status(f"Spec error: {exc}", "error")

        self._run_background(load_work, on_loaded, on_error)

    def _populate_spec_selector(self, specs: List[Path], select_first: bool) -> None:
        if self.spec_selector is None:
            return
        current = self.spec_selector.currentData() if self.spec_selector.count() else None  # type: ignore[attr-defined]
        self.spec_selector.blockSignals(True)  # type: ignore[attr-defined]
        self.spec_selector.clear()  # type: ignore[attr-defined]
        for path in specs:
            self.spec_selector.addItem(self._format_spec_label(path), str(path))  # type: ignore[attr-defined]
        self.spec_selector.blockSignals(False)  # type: ignore[attr-defined]

        if select_first and specs:
            self.spec_selector.setCurrentIndex(0)  # type: ignore[attr-defined]
            self.spec_edit.setText(str(specs[0]))
        elif current:
            index = self.spec_selector.findData(current)  # type: ignore[attr-defined]
            if index >= 0:
                self.spec_selector.setCurrentIndex(index)  # type: ignore[attr-defined]

        if specs:
            message = f"Discovered {len(specs)} suite spec(s)."
            self.set_status(message, "idle")
        else:
            self.set_status(
                "No suite specs found under docs/examples or docs/benchmarks.",
                "error",
            )

    def _ensure_selector_entry(self, path: Path) -> None:
        if self.spec_selector is None:
            return
        text = str(path)
        for idx in range(self.spec_selector.count()):  # type: ignore[attr-defined]
            if self.spec_selector.itemData(idx) == text:  # type: ignore[attr-defined]
                return
        self.spec_selector.addItem(self._format_spec_label(path), text)  # type: ignore[attr-defined]

    def _render_spec(self, spec: BatchSpec, path: Path) -> None:
        self.summary_label.setText(
            f"{len(spec.jobs)} jobs → {path.name}"
        )
        self.summary_view.setPlainText(self._format_spec_details(spec))
        self._populate_jobs(spec)
        self.analysis_view.setPlainText("Select a job and run analysis to view workload DNA.")

    def _format_spec_details(self, spec: BatchSpec) -> str:
        lines: List[str] = []
        lines.append(f"Working directory: {self._relativize(spec.working_dir)}")
        lines.append(f"CLI path: {self._relativize(spec.hashmap_cli)}")
        lines.append(f"Report: {self._relativize(spec.report_path)}")
        if spec.html_report_path:
            lines.append(f"HTML report: {self._relativize(spec.html_report_path)}")
        lines.append("")
        lines.append("Jobs:")
        for job in spec.jobs:
            summary = f"  • {job.name} → {job.command} ({job.mode})"
            summary += f"\n    CSV: {self._relativize(job.csv)}"
            if job.json_summary:
                summary += f"\n    Summary: {self._relativize(job.json_summary)}"
            if job.metrics_out_dir:
                summary += f"\n    Metrics dir: {self._relativize(job.metrics_out_dir)}"
            if job.extra_args:
                summary += f"\n    Extra args: {' '.join(job.extra_args)}"
            lines.append(summary)
        return "\n".join(lines)

    @staticmethod
    def _relativize(path: Path | None) -> str:
        if path is None:
            return "-"
        try:
            resolved = path.resolve()
            cwd = Path.cwd().resolve()
            return str(resolved.relative_to(cwd))
        except Exception:
            return str(path)

    def _populate_jobs(self, spec: BatchSpec) -> None:
        self._job_lookup = {job.name: job for job in spec.jobs}
        self._job_order = list(spec.jobs)
        if self.job_selector is None:
            return
        self.job_selector.blockSignals(True)  # type: ignore[attr-defined]
        self.job_selector.clear()  # type: ignore[attr-defined]
        for job in spec.jobs:
            label = job.name or job.csv.stem
            self.job_selector.addItem(label, job)  # type: ignore[attr-defined]
        if not spec.jobs:
            self.job_selector.addItem("(no jobs)", None)  # type: ignore[attr-defined]
        self.job_selector.blockSignals(False)  # type: ignore[attr-defined]
        if spec.jobs:
            self.job_selector.setCurrentIndex(0)  # type: ignore[attr-defined]

    def _select_job(self, job: JobSpec) -> None:
        if self.job_selector is None:
            return
        for idx in range(self.job_selector.count()):  # type: ignore[attr-defined]
            data = self.job_selector.itemData(idx)  # type: ignore[attr-defined]
            if isinstance(data, JobSpec) and data.name == job.name:
                self.job_selector.setCurrentIndex(idx)  # type: ignore[attr-defined]
                return

    def _get_selected_job(self) -> Optional[JobSpec]:
        if self.job_selector is not None and self.job_selector.count():  # type: ignore[attr-defined]
            data = self.job_selector.currentData()  # type: ignore[attr-defined]
            if isinstance(data, JobSpec):
                return data
            if isinstance(data, str):
                return self._job_lookup.get(data)
        return self._job_order[0] if self._job_order else None

    def _on_analyze_clicked(self) -> None:
        job = self._get_selected_job()
        if job is None:
            self._show_analysis_message("No jobs available to analyze.", error=True)
            return
        if not job.csv.exists():
            self._show_analysis_message(f"CSV not found: {job.csv}", error=True)
            return
        try:
            result = analyze_workload_csv(job.csv, top_keys=8)
        except BadInputError as exc:
            self._show_analysis_message(str(exc), error=True)
            return
        except Exception as exc:  # pragma: no cover - defensive guard
            self._show_analysis_message(f"Analysis failed: {exc}", error=True)
            return

        summary = format_workload_dna(result)
        self.analysis_view.setPlainText(summary)
        self.set_status(f"Analyzed {job.name}", "idle")
        spec_path = self._current_spec_path or job.csv.parent
        self._emit_analysis(result, job, spec_path)

    def _show_analysis_message(self, message: str, *, error: bool = False) -> None:
        self.analysis_view.setPlainText(message)
        if error:
            self.set_status(message, "error")

    def get_spec_path(self) -> Optional[Path]:
        text = self.spec_edit.text().strip()
        if not text:
            return None
        return Path(text).expanduser()

    def add_analysis_callback(
        self, callback: Callable[[WorkloadDNAResult, JobSpec, Path], None]
    ) -> None:
        self._analysis_callbacks.append(callback)

    def clear_log(self) -> None:
        self.log_view.clear()

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self._start_timer()
        else:
            self._stop_timer()

    def indicate_stopping(self) -> None:
        self.set_status("Stopping…", "stopping")

    def prepare_for_run(self, spec_path: Path, spec: BatchSpec) -> None:
        self._active_spec_path = spec_path
        self._active_spec = spec
        self.clear_log()
        self.spec_edit.setText(str(spec_path))
        self._ensure_selector_entry(spec_path)
        self._render_spec(spec, spec_path)
        if spec.jobs:
            self._select_job(spec.jobs[0])
        self.set_running(True)
        self.set_status(f"Running {spec_path.name}", "running")

    def finalize_run(self, exit_code: int) -> None:
        state = "completed" if exit_code == 0 else "error"
        label = "Completed" if exit_code == 0 else f"Exited ({exit_code})"
        self.set_running(False)
        self.set_status(label, state)
        if self._active_spec_path and self._active_spec:
            self._append_history_entry(self._active_spec_path, self._active_spec, exit_code)
        self._active_spec_path = None
        self._active_spec = None

    def _append_history_entry(self, spec_path: Path, spec: BatchSpec, exit_code: int) -> None:
        timestamp = time.strftime("%H:%M:%S")
        report = self._relativize(spec.report_path)
        status = "ok" if exit_code == 0 else f"exit {exit_code}"
        lines = [
            f"[{timestamp}] {spec_path.name} → {status}",
            f"  report: {report}",
        ]
        if spec.html_report_path:
            lines.append(f"  html: {self._relativize(spec.html_report_path)}")
        entry = "\n".join(lines)
        self._history.append(entry)
        if len(self._history) > self._HISTORY_LIMIT:
            self._history = self._history[-self._HISTORY_LIMIT :]
        self.history_view.setPlainText("\n\n".join(reversed(self._history)))

    def _start_timer(self) -> None:
        self._start_time = time.monotonic()
        self.timer_label.setText("Elapsed: 0.0s")
        if self._timer is not None:
            self._timer.start()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._start_time is not None:
            elapsed = time.monotonic() - self._start_time
            self.timer_label.setText(f"Elapsed: {elapsed:.1f}s")
        else:
            self.timer_label.setText("Elapsed: 0.0s")
        self._start_time = None

    def _on_timer_tick(self) -> None:
        if self._start_time is None:
            return
        elapsed = time.monotonic() - self._start_time
        self.timer_label.setText(f"Elapsed: {elapsed:.1f}s")

    def _emit_analysis(self, result: WorkloadDNAResult, job: JobSpec, spec_path: Path) -> None:
        if self.analysisCompleted is not None:  # type: ignore[truthy-bool]
            try:
                self.analysisCompleted.emit(result, job, spec_path)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        for callback in list(self._analysis_callbacks):
            callback(result, job, spec_path)


class WorkloadDNAPane(QWidget):  # type: ignore[misc]
    """Visualise Workload DNA analysis with interactive charts."""

    _VIEW_HEATMAP = "Heatmap"
    _VIEW_BUCKETS_ID = "Buckets (by ID)"
    _VIEW_BUCKETS_SORTED = "Buckets (sorted by depth)"
    _VIEW_DEPTH = "Depth histogram"
    _DEFAULT_LIMIT = 32

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "dna")

        self._supports_charts = Qt is not None and pg is not None and np is not None
        self._primary_plot: Optional[pg.PlotWidget] = None  # type: ignore[assignment]
        self._comparison_plot: Optional[pg.PlotWidget] = None  # type: ignore[assignment]
        self._current_result: Optional[WorkloadDNAResult] = None
        self._current_label: str = ""
        self._baseline_result: Optional[WorkloadDNAResult] = None
        self._baseline_label: Optional[str] = None
        self._bucket_limit = self._DEFAULT_LIMIT
        self._view_mode = self._VIEW_BUCKETS_ID
        self._bucket_entries: List[Tuple[int, str, int, float]] = []
        self._bucket_total: float = 0.0
        self._heatmap_counts: Optional[List[float]] = None
        self._heatmap_side: int = 0
        self._heatmap_total: float = 0.0
        self._heatmap_image: Optional[Any] = None
        self._heatmap_overlay: Optional[Any] = None
        self._hover_bucket_index: Optional[int] = None
        self._hover_heatmap_index: Optional[int] = None

        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Workload DNA")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        self.summary_label = QLabel("No workload analyzed yet.")  # type: ignore[call-arg]
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("dnaSummaryLabel")
        layout.addWidget(self.summary_label)

        controls = QHBoxLayout()  # type: ignore[call-arg]

        self.view_combo = None
        if QComboBox is not None:
            combo = QComboBox()  # type: ignore[call-arg]
            self.view_combo = combo
            combo.setObjectName("dnaViewSelector")
            combo.blockSignals(True)
            for label in (
                    self._VIEW_HEATMAP,
                    self._VIEW_BUCKETS_ID,
                    self._VIEW_BUCKETS_SORTED,
                    self._VIEW_DEPTH,
            ):
                combo.addItem(label)
            combo.setCurrentText(self._view_mode)
            combo.blockSignals(False)
            combo.currentTextChanged.connect(self._on_view_changed)  # type: ignore[attr-defined]
            controls.addWidget(combo)

        self.bucket_limit_spin = None
        if QSpinBox is not None:
            spin = QSpinBox()  # type: ignore[call-arg]
            self.bucket_limit_spin = spin
            spin.setObjectName("dnaBucketLimit")
            spin.setRange(8, 512)
            spin.setValue(self._DEFAULT_LIMIT)
            spin.setSingleStep(8)
            spin.valueChanged.connect(self._on_bucket_limit_changed)  # type: ignore[attr-defined]
            controls.addWidget(QLabel("Top buckets:"))  # type: ignore[call-arg]
            controls.addWidget(spin)

        controls.addStretch()  # type: ignore[attr-defined]

        self.pin_baseline_button = QPushButton("Pin as baseline")  # type: ignore[call-arg]
        self.pin_baseline_button.setObjectName("dnaPinBaseline")
        self.pin_baseline_button.clicked.connect(self._on_pin_baseline)  # type: ignore[attr-defined]
        controls.addWidget(self.pin_baseline_button)

        self.clear_baseline_button = QPushButton("Clear baseline")  # type: ignore[call-arg]
        self.clear_baseline_button.setObjectName("dnaClearBaseline")
        self.clear_baseline_button.clicked.connect(self._on_clear_baseline)  # type: ignore[attr-defined]
        controls.addWidget(self.clear_baseline_button)

        self.compare_toggle = QCheckBox("Show comparison") if QCheckBox is not None else None  # type: ignore[call-arg]
        if self.compare_toggle is not None:
            self.compare_toggle.setObjectName("dnaCompareToggle")
            self.compare_toggle.stateChanged.connect(self._on_compare_toggled)  # type: ignore[attr-defined]
            controls.addWidget(self.compare_toggle)

        layout.addLayout(controls)

        self.baseline_label = QLabel("Baseline: none")  # type: ignore[call-arg]
        self.baseline_label.setObjectName("dnaBaselineLabel")
        self.baseline_label.setProperty("baselineSet", "false")
        layout.addWidget(self.baseline_label)

        if self._supports_charts:
            self._primary_plot = pg.PlotWidget(title="Primary")  # type: ignore[attr-defined]
            self._primary_plot.setObjectName("dnaPrimaryPlot")
            self._style_plot(self._primary_plot)

            self._comparison_plot = pg.PlotWidget(title="Baseline")  # type: ignore[attr-defined]
            self._comparison_plot.setObjectName("dnaComparisonPlot")
            self._style_plot(self._comparison_plot)
            self._comparison_plot.hide()

            plot_layout = QHBoxLayout()  # type: ignore[call-arg]
            plot_layout.addWidget(self._primary_plot)
            plot_layout.addWidget(self._comparison_plot)
            layout.addLayout(plot_layout)
        else:
            fallback = QLabel("PyQtGraph/Numpy not available – visuals disabled.")  # type: ignore[call-arg]
            fallback.setObjectName("dnaFallbackLabel")
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
            self._primary_plot = None
            self._comparison_plot = None

        self.details_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.details_view.setObjectName("dnaDetailsView")
        self.details_view.setReadOnly(True)
        self.details_view.setMaximumBlockCount(500)
        layout.addWidget(self.details_view)

        if self._supports_charts and self._primary_plot is not None:
            self._primary_plot.scene().sigMouseMoved.connect(self._on_primary_hover)  # type: ignore[attr-defined]

    def set_primary_result(self, result: WorkloadDNAResult, label: str, spec_path: Path) -> None:
        self._current_result = result
        self._current_label = label
        self.summary_label.setText(f"{label} — {spec_path.name}")
        self.details_view.setPlainText(format_workload_dna(result))
        self._render_all()

    def pin_baseline(self, result: WorkloadDNAResult, label: str) -> None:
        self._baseline_result = result
        self._baseline_label = label
        self.baseline_label.setText(f"Baseline: {label}")
        self.baseline_label.setProperty("baselineSet", "true")
        self._repolish(self.baseline_label)
        if self.compare_toggle is not None:
            self.compare_toggle.setChecked(True)
        self._render_all()

    def clear_baseline(self) -> None:
        self._baseline_result = None
        self._baseline_label = None
        self.baseline_label.setText("Baseline: none")
        self.baseline_label.setProperty("baselineSet", "false")
        self._repolish(self.baseline_label)
        if self._comparison_plot is not None:
            self._comparison_plot.clear()
            self._comparison_plot.hide()
        if self.compare_toggle is not None:
            self.compare_toggle.setChecked(False)

    def _on_view_changed(self, mode: str) -> None:
        self._view_mode = mode
        self._hide_tooltip()
        self._render_all()

    def _on_bucket_limit_changed(self, value: int) -> None:
        self._bucket_limit = value
        if self._view_mode in {self._VIEW_BUCKETS_ID, self._VIEW_BUCKETS_SORTED}:
            self._render_all()

    def _on_pin_baseline(self) -> None:
        if self._current_result is None:
            return
        self.pin_baseline(self._current_result, self._current_label or "primary")

    def _on_clear_baseline(self) -> None:
        self.clear_baseline()

    def _on_compare_toggled(self, state: int) -> None:
        if state == 0 and self._comparison_plot is not None:
            self._comparison_plot.hide()
        self._render_all()

    def _repolish(self, widget: QWidget) -> None:
        if Qt is None:
            return
        style = widget.style()
        if style is None:  # pragma: no cover - headless fallback
            return
        style.unpolish(widget)  # type: ignore[attr-defined]
        style.polish(widget)  # type: ignore[attr-defined]

    def _render_all(self) -> None:
        primary_plot = self._primary_plot
        if not self._supports_charts or primary_plot is None:
            return
        self._render_plot(primary_plot, self._current_result, self._current_label or "Primary")
        comparison_plot = self._comparison_plot
        if (
            comparison_plot is not None
            and self._baseline_result is not None
            and self.compare_toggle is not None
            and self.compare_toggle.isChecked()
        ):
            comparison_plot.show()
            self._render_plot(
                comparison_plot,
                self._baseline_result,
                self._baseline_label or "Baseline",
            )
        elif comparison_plot is not None:
            comparison_plot.clear()
            comparison_plot.hide()

    def _render_plot(self, plot: Optional[pg.PlotWidget], result: Optional[WorkloadDNAResult], title: str) -> None:
        if plot is None:
            return
        plot.clear()
        plot.setTitle(title)
        if result is None:
            return
        if self._view_mode == self._VIEW_HEATMAP:
            self._render_heatmap(plot, result)
        elif self._view_mode == self._VIEW_BUCKETS_ID:
            self._render_bucket_chart(plot, result, mode=self._VIEW_BUCKETS_ID)
        elif self._view_mode == self._VIEW_BUCKETS_SORTED:
            self._render_bucket_chart(plot, result, mode=self._VIEW_BUCKETS_SORTED)
        elif self._view_mode == self._VIEW_DEPTH:
            self._render_depth_histogram(plot, result)

    def _render_bucket_chart(
        self,
        plot: pg.PlotWidget,
        result: WorkloadDNAResult,
        *,
        mode: str,
    ) -> None:
        if pg is None:
            return
        is_primary = plot is self._primary_plot
        if is_primary:
            self._hide_tooltip()
        top_entries = self._top_buckets(
            result,
            self._bucket_limit,
            store_total=is_primary,
        )
        if not top_entries:
            if is_primary:
                self._bucket_entries = []
            plot.getAxis("bottom").setTicks([])  # type: ignore[attr-defined]
            plot.getAxis("left").setTicks([])  # type: ignore[attr-defined]
            return

        if mode == self._VIEW_BUCKETS_ID:
            display_entries = sorted(top_entries, key=lambda entry: entry[0])
        else:
            display_entries = top_entries

        if is_primary:
            self._bucket_entries = display_entries
            self._hover_bucket_index = None

        plot.setAspectLocked(False)
        plot.invertY(False)  # type: ignore[attr-defined]
        plot.showAxis("bottom")  # type: ignore[attr-defined]
        plot.showAxis("left")  # type: ignore[attr-defined]

        xs = list(range(len(display_entries)))
        heights = [entry[2] for entry in display_entries]
        brushes = [self._density_brush(entry[3]) for entry in display_entries]
        bar_item = pg.BarGraphItem(x=xs, height=heights, width=0.8, brushes=brushes)
        plot.addItem(bar_item)
        plot.setXRange(-0.5, len(display_entries) - 0.5, padding=0.04)  # type: ignore[attr-defined]

        max_labels = 14
        step = max(1, len(display_entries) // max_labels)
        ticks: List[Tuple[int, str]] = []
        for idx, entry in enumerate(display_entries):
            should_label = idx % step == 0 or idx == len(display_entries) - 1
            if not should_label:
                continue
            if mode == self._VIEW_BUCKETS_ID:
                ticks.append((idx, entry[1]))
            else:
                ticks.append((idx, str(idx + 1)))
        plot.getAxis("bottom").setTicks([ticks])  # type: ignore[attr-defined]

        plot.setLabel("left", "Keys in bucket")  # type: ignore[attr-defined]
        if mode == self._VIEW_BUCKETS_ID:
            plot.setLabel("bottom", "Bucket ID (hex)")  # type: ignore[attr-defined]
        else:
            plot.setLabel("bottom", "Bucket rank (1..N)")  # type: ignore[attr-defined]
        plot.enableAutoRange(axis="y", enable=True)  # type: ignore[attr-defined]

    def _render_heatmap(self, plot: pg.PlotWidget, result: WorkloadDNAResult) -> None:
        if pg is None or np is None:
            return
        is_primary = plot is self._primary_plot
        counts = np.array(result.bucket_counts, dtype=float)
        total = float(np.sum(counts)) if counts.size else 0.0
        if counts.size == 0:
            if is_primary:
                self._heatmap_counts = None
                self._heatmap_total = 0.0
                self._heatmap_side = 0
                self._heatmap_image = None
                self._hover_heatmap_index = None
                self._set_heatmap_overlay(plot, "No bucket data yet.")
            plot.hideAxis("bottom")  # type: ignore[attr-defined]
            plot.hideAxis("left")  # type: ignore[attr-defined]
            plot_item = plot.getPlotItem()
            if plot_item is not None:
                plot_item.setRange(xRange=(0, 1), yRange=(0, 1), padding=0.0)  # type: ignore[attr-defined]
            return

        side = int(math.ceil(math.sqrt(counts.size)))
        if counts.size < side * side:
            pad = side * side - counts.size
            counts = np.pad(counts, (0, pad))
        grid = counts.reshape(side, side)

        clip = result.bucket_percentiles.get("p95", 0.0)
        try:
            max_value = float(np.max(grid))
        except Exception:
            max_value = 0.0
        if clip is None or not isinstance(clip, (int, float)) or clip <= 0.0:
            clip_value = max_value if max_value > 0.0 else 1.0
        else:
            clip_value = float(clip)
            if clip_value <= 0.0:
                clip_value = max_value if max_value > 0.0 else 1.0
            elif max_value > clip_value:
                # soften the clamp when p95 underestimates the active range
                clip_value = max(clip_value, max_value * 0.75)
        grid = np.clip(grid, 0.0, max(clip_value, 1.0))

        cmap = pg.ColorMap(
            [0.0, 0.5, 1.0],
            [
                (0, 255, 170),
                (255, 214, 102),
                (255, 64, 64),
            ],
        )

        img = pg.ImageItem(grid.T)
        img.setLookupTable(cmap.getLookupTable())
        img.setLevels((0.0, max(clip_value, max_value, 1.0)))
        plot.addItem(img)
        plot.invertY(False)  # type: ignore[attr-defined]
        plot.setAspectLocked(True, ratio=1)
        plot.hideAxis("bottom")  # type: ignore[attr-defined]
        plot.hideAxis("left")  # type: ignore[attr-defined]
        plot_item = plot.getPlotItem()
        if plot_item is not None:
            view_box = plot_item.getViewBox()
            if view_box is not None:
                view_box.setLimits(xMin=0.0, yMin=0.0)  # type: ignore[attr-defined]
            plot_item.setRange(xRange=(0, side), yRange=(0, side), padding=0.0)  # type: ignore[attr-defined]

        if is_primary:
            self._heatmap_counts = list(result.bucket_counts)
            self._heatmap_side = side
            self._heatmap_total = total
            self._heatmap_image = img
            self._hover_heatmap_index = None
            if total <= 0.0:
                self._set_heatmap_overlay(plot, "All buckets empty (no keys yet).")
            else:
                self._set_heatmap_overlay(plot, None)

    def _render_depth_histogram(self, plot: pg.PlotWidget, result: WorkloadDNAResult) -> None:
        if pg is None:
            return
        histogram = result.collision_depth_histogram
        if not histogram:
            return
        plot.setAspectLocked(False)
        plot.invertY(False)  # type: ignore[attr-defined]
        plot.showAxis("bottom")  # type: ignore[attr-defined]
        plot.showAxis("left")  # type: ignore[attr-defined]
        depths = sorted(histogram.keys())
        counts = [histogram[d] for d in depths]
        max_depth = max(depths) if depths else 1
        denom = max(1, max_depth)
        brushes = [self._density_brush(depth / denom) for depth in depths]
        bar = pg.BarGraphItem(x=depths, height=counts, width=0.8, brushes=brushes)
        plot.addItem(bar)
        plot.setLabel("bottom", "Keys per bucket (depth)")  # type: ignore[attr-defined]
        plot.setLabel("left", "Bucket count")  # type: ignore[attr-defined]
        plot.enableAutoRange(axis="xy", enable=True)  # type: ignore[attr-defined]
        plot.autoRange()  # type: ignore[attr-defined]

    def _top_buckets(
        self,
        result: WorkloadDNAResult,
        limit: int,
        *,
        store_total: bool = True,
    ) -> List[Tuple[int, str, int, float]]:
        counts = list(result.bucket_counts)
        total = sum(counts)
        if store_total:
            self._bucket_total = float(total)
        if not counts or total <= 0:
            return []
        max_index = max(len(counts) - 1, 0)
        width = max(3, len(f"{max_index:x}"))
        buckets = list(enumerate(counts))
        buckets.sort(key=lambda item: item[1], reverse=True)
        limit = max(1, limit)
        entries: List[Tuple[int, str, int, float]] = []
        for idx, count in buckets:
            if count <= 0 and entries:
                break
            label = f"0x{idx:0{width}x}"
            share = (float(count) / float(total)) if total else 0.0
            entries.append((idx, label, int(count), share))
            if len(entries) >= limit:
                break
        return entries

    def _density_brush(self, ratio: float):
        if pg is None:
            return None
        ratio = max(0.0, min(1.0, ratio))
        hue = int(120 - 120 * ratio)
        color = QColor.fromHsv(hue, 255, 255)
        return pg.mkBrush(color)

    def _set_heatmap_overlay(self, plot: pg.PlotWidget, message: Optional[str]) -> None:
        if pg is None:
            return
        if message:
            if self._heatmap_overlay is None:
                self._heatmap_overlay = pg.TextItem(color="w", anchor=(0.5, 0.5))  # type: ignore[attr-defined]
            self._heatmap_overlay.setText(message)  # type: ignore[attr-defined]
            center = (max(self._heatmap_side, 1) / 2.0) if self._heatmap_side else 0.5
            self._heatmap_overlay.setPos(center, center)  # type: ignore[attr-defined]
            if self._heatmap_overlay not in plot.items:
                plot.addItem(self._heatmap_overlay)
        elif self._heatmap_overlay is not None and self._heatmap_overlay in plot.items:
            plot.removeItem(self._heatmap_overlay)

    def _on_primary_hover(self, scene_pos: Any) -> None:
        primary_plot = self._primary_plot
        if (
            primary_plot is None
            or QToolTip is None
            or Qt is None
            or pg is None
        ):
            return
        if self._view_mode == self._VIEW_HEATMAP:
            handled = self._handle_heatmap_hover(scene_pos)
        elif self._view_mode in {self._VIEW_BUCKETS_ID, self._VIEW_BUCKETS_SORTED}:
            handled = self._handle_bucket_hover(scene_pos)
        else:
            handled = False
        if not handled:
            self._hide_tooltip()

    def _handle_heatmap_hover(self, scene_pos: Any) -> bool:
        primary_plot = self._primary_plot
        if (
            self._heatmap_image is None
            or self._heatmap_counts is None
            or self._heatmap_side <= 0
            or primary_plot is None
        ):
            return False
        plot_item = primary_plot.getPlotItem()
        if plot_item is None:
            return False
        view_box = plot_item.getViewBox()
        if view_box is None:
            return False
        point = view_box.mapSceneToView(scene_pos)
        x = point.x()
        y = point.y()
        if x < 0 or y < 0 or x >= self._heatmap_side or y >= self._heatmap_side:
            return False
        column = int(x)
        row = int(y)
        orig_index = column * self._heatmap_side + row
        if orig_index >= len(self._heatmap_counts):
            return False
        if self._hover_heatmap_index == orig_index:
            return True
        self._hover_heatmap_index = orig_index
        count = float(self._heatmap_counts[orig_index])
        count_display = int(round(count))
        total = self._heatmap_total if self._heatmap_total > 0 else None
        share = (count / total) if total else None
        max_index = max(len(self._heatmap_counts) - 1, 0)
        width = max(3, len(f"{max_index:x}"))
        bucket_label = f"0x{orig_index:0{width}x}"
        if share is not None:
            tooltip = f"{bucket_label} → {count_display} keys ({self._format_share(share)})"
        else:
            tooltip = f"{bucket_label} → {count_display} keys"
        QToolTip.showText(QCursor.pos(), tooltip, primary_plot)
        return True

    def _handle_bucket_hover(self, scene_pos: Any) -> bool:
        primary_plot = self._primary_plot
        if primary_plot is None or not self._bucket_entries:
            return False
        plot_item = primary_plot.getPlotItem()
        if plot_item is None:
            return False
        view_box = plot_item.getViewBox()
        if view_box is None:
            return False
        point = view_box.mapSceneToView(scene_pos)
        x = point.x()
        if not (-0.6 <= x <= len(self._bucket_entries) - 0.4):
            return False
        index = int(round(x))
        if index < 0 or index >= len(self._bucket_entries):
            return False
        if abs(x - index) > 0.55:
            return False
        if self._hover_bucket_index == index:
            return True
        bucket_index, bucket_label, count, share = self._bucket_entries[index]
        if self._view_mode == self._VIEW_BUCKETS_SORTED:
            rank = index + 1
            tooltip = (
                f"Rank {rank}: {count} keys ({self._format_share(share)})"
                f" — bucket {bucket_label}"
            )
        else:
            tooltip = f"{bucket_label} → {count} keys ({self._format_share(share)})"
        self._hover_bucket_index = index
        QToolTip.showText(QCursor.pos(), tooltip, primary_plot)
        return True

    def _hide_tooltip(self) -> None:
        if QToolTip is None:
            return
        if self._hover_heatmap_index is not None or self._hover_bucket_index is not None:
            self._hover_heatmap_index = None
            self._hover_bucket_index = None
            QToolTip.hideText()

    def _format_share(self, share: float) -> str:
        if share <= 0.0:
            return "0"
        if share >= 0.001:
            return f"{share * 100:.2f}%"
        return f"{share * 10000:.1f} bp"

    def _style_plot(self, plot: pg.PlotWidget) -> None:
        if pg is None:
            return
        plot.setBackground("#121212")
        plot.getAxis("left").setPen(pg.mkPen("#334155"))  # type: ignore[attr-defined]
        plot.getAxis("left").setTextPen(pg.mkPen("#94a3b8"))  # type: ignore[attr-defined]
        plot.getAxis("bottom").setPen(pg.mkPen("#334155"))  # type: ignore[attr-defined]
        plot.getAxis("bottom").setTextPen(pg.mkPen("#94a3b8"))  # type: ignore[attr-defined]
