# mypy: ignore-errors
"""Controller glue between widgets and metrics client."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from adhash.batch.runner import BatchSpec, JobSpec, load_spec
from adhash.workloads import WorkloadDNAResult

from .metrics_client import HttpPoller, MetricsSnapshot
from .process_manager import ProcessManager
from .widgets import (
    ConfigEditorPane,
    ConnectionPane,
    MetricsPane,
    RunControlPane,
    BenchmarkSuitePane,
    WorkloadDNAPane,
)

try:  # pragma: no cover - only available when PyQt6 is installed
    from PyQt6.QtCore import QObject, pyqtSignal  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - headless environments
    QObject = None  # type: ignore[assignment]
    pyqtSignal = None  # type: ignore[assignment]


if QObject is not None:  # pragma: no cover - requires PyQt6
    class _UiBridge(QObject):  # type: ignore[misc]
        call = pyqtSignal(object)

        def __init__(self) -> None:
            super().__init__()
            self.call.connect(self._dispatch)  # type: ignore[attr-defined]

        def submit(self, func: Callable[..., None], *args, **kwargs) -> None:
            self.call.emit((func, args, kwargs))  # type: ignore[attr-defined]

        def _dispatch(self, payload: object) -> None:
            if not isinstance(payload, tuple):
                return
            func, args, kwargs = payload
            if callable(func):
                func(*args, **kwargs)
else:  # pragma: no cover - PyQt6 missing
    class _UiBridge:
        def submit(self, func: Callable[..., None], *args, **kwargs) -> None:
            func(*args, **kwargs)


class MissionControlController:
    def __init__(
        self,
        connection: ConnectionPane,
        metrics: MetricsPane,
        run_control: RunControlPane,
        config_editor: Optional[ConfigEditorPane] = None,
        suite_manager: Optional[BenchmarkSuitePane] = None,
        dna_panel: Optional[WorkloadDNAPane] = None,
        poll_interval: float = 2.0,
    ) -> None:
        self._connection = connection
        self._metrics = metrics
        self._run_control = run_control
        self._config_editor = config_editor
        self._suite_pane = suite_manager
        self._dna_pane = dna_panel
        self._poll_interval = poll_interval
        self._poller: Optional[HttpPoller] = None
        self._process = ProcessManager(self._handle_process_output, self._handle_process_exit)
        self._suite_process = ProcessManager(self._handle_suite_output, self._handle_suite_exit)
        self._active_suite_spec: Optional[BatchSpec] = None
        self._active_suite_path: Optional[Path] = None
        self._ui = _UiBridge()

        self._connection.connect_button.clicked.connect(self._on_connect_clicked)  # type: ignore[attr-defined]
        self._run_control.start_button.clicked.connect(self._on_run_start)  # type: ignore[attr-defined]
        self._run_control.stop_button.clicked.connect(self._on_run_stop)  # type: ignore[attr-defined]

        if self._config_editor is not None:
            try:
                self._config_editor.add_config_saved_callback(self._handle_config_saved)
                self._config_editor.add_config_loaded_callback(self._handle_config_loaded)
            except AttributeError:
                pass

        if self._suite_pane is not None:
            self._suite_pane.run_button.clicked.connect(self._on_suite_run)  # type: ignore[attr-defined]
            self._suite_pane.stop_button.clicked.connect(self._on_suite_stop)  # type: ignore[attr-defined]
            self._suite_pane.add_analysis_callback(self._handle_workload_analysis)

    def shutdown(self) -> None:
        if self._poller:
            self._poller.stop()
            self._poller = None
        self._process.stop()
        self._suite_process.stop()

    def _on_connect_clicked(self) -> None:
        if self._poller:
            self._poller.stop()
            self._poller = None
            self._connection.set_status("Disconnected", "idle")
            self._connection.connect_button.setText("Connect")  # type: ignore[attr-defined]
            return

        host = self._connection.host_edit.text()  # type: ignore[attr-defined]
        port_raw = self._connection.port_edit.text()  # type: ignore[attr-defined]
        try:
            port = int(port_raw)
        except ValueError:
            self._connection.set_status("Invalid port", "error")
            return

        poller = HttpPoller(host, port, interval=self._poll_interval)
        poller.on_snapshot = self._handle_snapshot
        poller.on_error = self._handle_error
        poller.start()
        self._poller = poller
        self._connection.set_status("Connected", "connected")
        self._connection.connect_button.setText("Disconnect")  # type: ignore[attr-defined]

    def _handle_snapshot(self, snapshot: MetricsSnapshot) -> None:
        self._ui.submit(self._metrics.update_snapshot, snapshot)

    def _handle_error(self, exc: Exception) -> None:
        self._ui.submit(self._connection.set_status, f"Error: {exc}", "error")
        self._ui.submit(self._connection.connect_button.setText, "Connect")  # type: ignore[attr-defined]
        if self._poller:
            self._poller.stop()
            self._poller = None

    def _on_run_start(self) -> None:
        if self._process.is_running():
            self._run_control.append_log("Process already running")
            return
        command_text = self._run_control.command_edit.text()  # type: ignore[attr-defined]
        command = command_text.strip()
        if not command:
            self._run_control.append_log("Enter a command to run.")
            return
        try:
            args = ProcessManager.parse_command(command)
        except ValueError as exc:
            self._run_control.append_log(f"Command parse error: {exc}")
            return
        if not args:
            self._run_control.append_log("Command is empty.")
            return
        try:
            self._process.start(args)
            self._run_control.set_running(True)
            self._run_control.append_log(f"Started: {' '.join(args)}")
        except Exception as exc:  # noqa: BLE001
            self._run_control.append_log(f"Failed to start: {exc}")

    def _on_run_stop(self) -> None:
        if not self._process.is_running():
            return
        self._run_control.append_log("Stopping process…")
        self._run_control.indicate_stopping()
        self._process.stop()
        self._run_control.set_running(False)

    def _handle_process_output(self, line: str) -> None:
        self._ui.submit(self._run_control.append_log, line)

    def _handle_process_exit(self, code: int) -> None:
        def _update() -> None:
            self._run_control.append_log(f"Process exited with code {code}")
            self._run_control.set_running(False)
            self._run_control.mark_exit(code)

        self._ui.submit(_update)

    def _handle_config_saved(self, path: str) -> None:
        self._ui.submit(self._run_control.apply_config_path, path)

    def _handle_config_loaded(self, path: str) -> None:
        self._ui.submit(self._run_control.apply_config_path, path)

    def _on_suite_run(self) -> None:
        if self._suite_pane is None:
            return
        if self._suite_process.is_running():
            self._suite_pane.append_log("Suite already running.")
            return

        spec_path = self._suite_pane.get_spec_path()
        if spec_path is None:
            self._suite_pane.set_status("Enter a spec path to run.", "error")
            return

        try:
            spec = load_spec(spec_path)
        except Exception as exc:
            self._suite_pane.set_status(f"Spec error: {exc}", "error")
            return

        self._suite_pane.prepare_for_run(spec_path, spec)
        self._suite_pane.append_log(f"Launching suite via batch runner: {spec_path}")
        self._active_suite_spec = spec
        self._active_suite_path = spec_path

        command = [sys.executable, "-m", "adhash.batch", "--spec", str(spec_path)]
        try:
            self._suite_process.start(command)
        except Exception as exc:  # noqa: BLE001
            self._suite_pane.append_log(f"Failed to start suite: {exc}")
            self._suite_pane.set_running(False)
            self._suite_pane.set_status(f"Launch error: {exc}", "error")
            self._active_suite_spec = None
            self._active_suite_path = None

    def _on_suite_stop(self) -> None:
        if self._suite_pane is None:
            return
        if not self._suite_process.is_running():
            self._suite_pane.append_log("No suite process is running.")
            return
        self._suite_pane.append_log("Stopping suite…")
        self._suite_pane.indicate_stopping()
        self._suite_process.stop()

    def _handle_suite_output(self, line: str) -> None:
        if self._suite_pane is None:
            return
        self._ui.submit(self._suite_pane.append_log, line)

    def _handle_suite_exit(self, code: int) -> None:
        if self._suite_pane is None:
            return

        def _update() -> None:
            self._suite_pane.append_log(f"Suite exited with code {code}")
            self._suite_pane.finalize_run(code)
            self._active_suite_spec = None
            self._active_suite_path = None

        self._ui.submit(_update)

    def _handle_workload_analysis(self, result: WorkloadDNAResult, job: JobSpec, spec_path: Path) -> None:
        if self._dna_pane is None:
            return

        def _update() -> None:
            self._dna_pane.set_primary_result(result, job.name, spec_path)

        self._ui.submit(_update)
