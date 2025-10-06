"""Run control pane for launching benchmark commands."""

from __future__ import annotations

import shlex
import time
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..process_manager import ProcessManager
from .common import (
    QColor,
    QGraphicsDropShadowEffect,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
)


class _RunStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


class RunControlPane(QWidget):  # type: ignore[misc]
    """Controls for launching run-csv commands."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "run")
        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        heading = QLabel("Run Command")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        self.config_label = QLabel("Config: (not set)")  # type: ignore[call-arg]
        self.config_label.setObjectName("configBindingLabel")
        self.config_label.setProperty("statusKind", "idle")
        self.config_label.setWordWrap(True)  # type: ignore[attr-defined]
        layout.addWidget(self.config_label)
        self._set_config_label(None)

        self.command_edit = QLineEdit(
            "python -m hashmap_cli --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090"
        )  # type: ignore[call-arg]
        self.start_button = QPushButton("Start run-csv")  # type: ignore[call-arg]
        self.start_button.setObjectName("startButton")
        self.stop_button = QPushButton("Stop")  # type: ignore[call-arg]
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.log_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("runLog")
        status_row = QHBoxLayout()  # type: ignore[call-arg]
        self.status_label = QLabel("Idle")  # type: ignore[call-arg]
        self.status_label.setObjectName("statusLabel")
        self.status_label.setProperty("state", "idle")
        self.timer_label = QLabel("Elapsed: 0.0s")  # type: ignore[call-arg]
        self.timer_label.setObjectName("timerLabel")
        status_row.addWidget(self.status_label)
        status_row.addStretch()  # type: ignore[attr-defined]
        status_row.addWidget(self.timer_label)
        self._timer = QTimer(self) if QTimer is not None else None
        if self._timer is not None:
            self._timer.setInterval(200)
            self._timer.timeout.connect(self._on_timer_tick)  # type: ignore[attr-defined]
        self._start_time: Optional[float] = None
        self._state = _RunStatus.IDLE
        layout.addWidget(self.command_edit)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addLayout(status_row)
        layout.addWidget(self.log_view)

        builder_heading = QLabel("Command builder")  # type: ignore[call-arg]
        builder_heading.setObjectName("paneSubheading")
        layout.addWidget(builder_heading)

        builder_form = QFormLayout()  # type: ignore[call-arg]
        builder_form.setContentsMargins(4, 4, 4, 4)
        self.exec_edit = QLineEdit("python -m hashmap_cli")  # type: ignore[call-arg]
        self.config_builder_edit = QLineEdit()  # type: ignore[call-arg]
        self.mode_edit = QLineEdit("adaptive")  # type: ignore[call-arg]
        self.csv_edit = QLineEdit("data/workloads/w_uniform.csv")  # type: ignore[call-arg]
        self.metrics_port_edit = QLineEdit("9090")  # type: ignore[call-arg]
        self.extra_args_edit = QLineEdit()  # type: ignore[call-arg]

        builder_form.addRow("Executable", self.exec_edit)
        builder_form.addRow("Config", self.config_builder_edit)
        builder_form.addRow("Mode", self.mode_edit)
        builder_form.addRow("CSV path", self.csv_edit)
        builder_form.addRow("Metrics port", self.metrics_port_edit)
        builder_form.addRow("Extra args", self.extra_args_edit)
        layout.addLayout(builder_form)

        builder_buttons = QHBoxLayout()  # type: ignore[call-arg]
        self.builder_parse_button = QPushButton("Parse command")  # type: ignore[call-arg]
        self.builder_apply_button = QPushButton("Update command")  # type: ignore[call-arg]
        builder_buttons.addStretch()  # type: ignore[attr-defined]
        builder_buttons.addWidget(self.builder_parse_button)
        builder_buttons.addWidget(self.builder_apply_button)
        layout.addLayout(builder_buttons)

        if Qt is not None and QGraphicsDropShadowEffect is not None:
            for button, color in (
                (self.start_button, "#00FFAA"),
                (self.stop_button, "#FF6B6B"),
            ):
                effect = QGraphicsDropShadowEffect(self)
                effect.setOffset(0, 0)
                effect.setBlurRadius(22)
                effect.setColor(QColor(color))
                button.setGraphicsEffect(effect)

        self.builder_parse_button.clicked.connect(self._populate_builder_from_command)  # type: ignore[attr-defined]
        self.builder_apply_button.clicked.connect(self._apply_builder_to_command)  # type: ignore[attr-defined]
        self._populate_builder_from_command()

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self._state = _RunStatus.RUNNING
            self._set_status("Running…", self._state.value)
            self._start_timer()
        else:
            self._stop_timer()
            if self._state not in (
                _RunStatus.STOPPING,
                _RunStatus.COMPLETED,
                _RunStatus.ERROR,
            ):
                self._state = _RunStatus.IDLE
                self._set_status("Idle", self._state.value)

    def indicate_stopping(self) -> None:
        self._state = _RunStatus.STOPPING
        self._set_status("Stopping…", self._state.value)

    def mark_exit(self, code: int) -> None:
        self._state = _RunStatus.COMPLETED if code == 0 else _RunStatus.ERROR
        status = "Completed" if self._state is _RunStatus.COMPLETED else f"Exited ({code})"
        self._set_status(status, self._state.value)
        self._stop_timer()

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

    def _set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self._repolish(self.status_label)

    def apply_config_path(self, path: str) -> None:
        """Update the command template and status label with ``--config`` path."""

        if not path:
            return
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = str(Path(path).expanduser())

        self._set_config_label(resolved)
        self.config_builder_edit.setText(resolved)

        text = self.command_edit.text().strip()
        if not text:
            default_command = [
                "python",
                "-m",
                "hashmap_cli",
                "--config",
                resolved,
                "run-csv",
                "--csv",
                "data/workloads/w_uniform.csv",
            ]
            self.command_edit.setText(" ".join(shlex.quote(part) for part in default_command))
            self._populate_builder_from_command()
            return

        try:
            args = list(ProcessManager.parse_command(text))
        except ValueError:
            self.command_edit.setText(f"{text} --config {shlex.quote(resolved)}")
            self._populate_builder_from_command()
            return

        if not args:
            args = ["python", "-m", "hashmap_cli"]

        if "--config" in args:
            idx = args.index("--config")
            if idx == len(args) - 1:
                args.append(resolved)
            else:
                args[idx + 1] = resolved
        else:
            args.extend(["--config", resolved])

        rebuilt = " ".join(shlex.quote(part) for part in args)
        self.command_edit.setText(rebuilt)
        self._populate_builder_from_command()

    def _set_config_label(self, value: Optional[str]) -> None:
        if value:
            text = f"Config: {value}"
            status = "connected"
        else:
            text = "Config: (not set)"
            status = "idle"
        self.config_label.setText(text)
        self.config_label.setProperty("statusKind", status)
        self._repolish(self.config_label)

    def _repolish(self, widget: QWidget) -> None:
        if Qt is None:
            return
        style = widget.style()
        if style is None:  # pragma: no cover - headless fallback
            return
        style.unpolish(widget)  # type: ignore[attr-defined]
        style.polish(widget)  # type: ignore[attr-defined]

    def _parse_command_args(self) -> Optional[List[str]]:
        text = self.command_edit.text().strip()
        if not text:
            return None
        try:
            return list(ProcessManager.parse_command(text))
        except ValueError:
            return None

    def _split_command(self, args: List[str]) -> Tuple[List[str], Dict[str, str], List[str], bool]:
        option_keys = {"--config", "--mode", "--csv", "--metrics-port"}
        exec_tokens: List[str] = []
        options: Dict[str, str] = {}
        extras: List[str] = []
        idx = 0
        while idx < len(args):
            token = args[idx]
            if token == "run-csv" or token in option_keys:
                break
            exec_tokens.append(token)
            idx += 1
        seen_run = False
        while idx < len(args):
            token = args[idx]
            if token == "run-csv":
                seen_run = True
                idx += 1
                continue
            if token in option_keys:
                value = args[idx + 1] if idx + 1 < len(args) else ""
                options[token] = value
                idx += 2 if idx + 1 < len(args) else 1
                continue
            extras.append(token)
            idx += 1
        if not exec_tokens and args:
            exec_tokens = [args[0]]
        return exec_tokens, options, extras, seen_run

    def _populate_builder_from_command(self) -> None:
        args = self._parse_command_args()
        if not args:
            return
        exec_tokens, options, extras, seen_run = self._split_command(args)
        self.exec_edit.setText(" ".join(exec_tokens))
        self.config_builder_edit.setText(options.get("--config", ""))
        self.mode_edit.setText(options.get("--mode", ""))
        self.csv_edit.setText(options.get("--csv", ""))
        self.metrics_port_edit.setText(options.get("--metrics-port", ""))
        self.extra_args_edit.setText(" ".join(extras))
        if options.get("--config"):
            self._set_config_label(options["--config"])
        elif self.config_builder_edit.text().strip() == "":
            self._set_config_label(None)
        if not seen_run:
            # If run-csv is missing, surface it in extra args so the builder can reinstate it.
            existing_extra = self.extra_args_edit.text().strip()
            if existing_extra:
                self.extra_args_edit.setText(f"run-csv {existing_extra}")
            else:
                self.extra_args_edit.setText("run-csv")

    def _apply_builder_to_command(self) -> None:
        exec_text = self.exec_edit.text().strip()
        exec_tokens = shlex.split(exec_text) if exec_text else ["python", "-m", "hashmap_cli"]

        config_value = self.config_builder_edit.text().strip()
        mode_value = self.mode_edit.text().strip()
        csv_value = self.csv_edit.text().strip()
        metrics_value = self.metrics_port_edit.text().strip()
        extras_text = self.extra_args_edit.text().strip()
        extra_tokens = shlex.split(extras_text) if extras_text else []

        parts: List[str] = list(exec_tokens)
        if config_value:
            parts += ["--config", config_value]
        if mode_value:
            parts += ["--mode", mode_value]
        parts.append("run-csv")
        if csv_value:
            parts += ["--csv", csv_value]
        if metrics_value:
            parts += ["--metrics-port", metrics_value]
        parts.extend(extra_tokens)

        self.command_edit.setText(" ".join(shlex.quote(part) for part in parts))
        self._set_config_label(config_value or None)
        self._populate_builder_from_command()
