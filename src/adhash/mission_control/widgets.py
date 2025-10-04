# mypy: ignore-errors
"""Reusable PyQt6 widgets for Mission Control."""

from __future__ import annotations

import time
import math
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    cast,
)

from adhash.batch.runner import BatchSpec, JobSpec, load_spec
from adhash.workloads import WorkloadDNAResult, analyze_workload_csv, format_workload_dna

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from .metrics_client import MetricsSnapshot

_QT_IMPORT_ERROR: Optional[Exception] = None

try:  # pragma: no cover - only when PyQt6 is present
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal
    from PyQt6.QtWidgets import (
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
        QHBoxLayout,
        QPlainTextEdit,
        QGraphicsDropShadowEffect,
        QTabWidget,
        QFormLayout,
        QComboBox,
        QCheckBox,
        QSpinBox,
        QToolTip,
    )
    from PyQt6.QtGui import QColor, QCursor
except Exception as exc:  # pragma: no cover - CI or headless environments
    _QT_IMPORT_ERROR = exc
    QLabel = cast(Any, object)
    QLineEdit = cast(Any, object)
    QPushButton = cast(Any, object)
    QWidget = cast(Any, object)
    QVBoxLayout = cast(Any, object)
    QHBoxLayout = cast(Any, object)
    QPlainTextEdit = cast(Any, object)
    QGraphicsDropShadowEffect = cast(Any, None)
    QTabWidget = cast(Any, None)
    QFormLayout = cast(Any, None)
    QComboBox = cast(Any, None)
    QCheckBox = cast(Any, None)
    QSpinBox = cast(Any, None)
    QToolTip = cast(Any, None)
    pyqtSignal = None  # type: ignore[assignment]
    QColor = cast(Any, object)
    QCursor = cast(Any, object)
    QTimer = cast(Any, None)
    Qt = None  # type: ignore[assignment]

try:  # pragma: no cover - optional plotting dependency
    import pyqtgraph as pg  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - charting optional
    pg = cast(Any, None)
else:  # pragma: no cover - requires PyQtGraph
    pg.setConfigOption("background", "#121212")
    pg.setConfigOption("foreground", "#EEEEEE")
    pg.setConfigOptions(antialias=True)

try:  # pragma: no cover - numpy optional at runtime but bundled with pyqtgraph
    import numpy as np  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback when numpy missing
    np = cast(Any, None)

from adhash.config import AppConfig
from adhash.config_toolkit import (
    CONFIG_FIELDS,
    FieldSpec,
    apply_updates_to_config,
    format_app_config_to_toml,
    list_presets,
    load_config_document,
    load_preset,
    resolve_presets_dir,
    save_preset,
)
from adhash.contracts.error import BadInputError
from .process_manager import ProcessManager

import shlex


__all__ = [
    "ConnectionPane",
    "RunControlPane",
    "ConfigEditorPane",
    "BenchmarkSuitePane",
    "MetricsPane",
    "WorkloadDNAPane",
    "extract_latency_histogram",
    "extract_probe_histogram",
]


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value in {None, "", "+Inf"}:
        if value == "+Inf":
            return math.inf
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_latency_histogram(
    payload: Mapping[str, Any],
    series: str = "overall",
) -> Sequence[Tuple[float, int]]:
    """Return per-bucket counts from a cumulative latency histogram payload."""

    operations = payload.get("operations")
    if not isinstance(operations, Mapping):
        return []
    raw_series = operations.get(series)
    if not isinstance(raw_series, Iterable):
        return []

    buckets: list[Tuple[float, int]] = []
    cumulative = 0
    for entry in raw_series:
        if not isinstance(entry, Mapping):
            continue
        upper = _safe_float(entry.get("le"))
        count = _safe_int(entry.get("count"))
        if upper is None or count is None:
            continue
        delta = max(count - cumulative, 0)
        cumulative = max(count, cumulative)
        buckets.append((upper, delta))
    return buckets


def extract_probe_histogram(payload: Mapping[str, Any]) -> Sequence[Tuple[int, int]]:
    """Normalise probe histogram payload to (distance, count) tuples."""

    buckets = payload.get("buckets")
    if not isinstance(buckets, Iterable):
        return []
    output: list[Tuple[int, int]] = []
    for entry in buckets:
        distance: Optional[int] = None
        count: Optional[int] = None
        if isinstance(entry, Mapping):
            distance = _safe_int(entry.get("distance"))
            count = _safe_int(entry.get("count"))
        elif isinstance(entry, (list, tuple)) and len(entry) == 2:
            distance = _safe_int(entry[0])
            count = _safe_int(entry[1])
        if distance is None or count is None:
            continue
        output.append((distance, count))
    return output


def _style_plot(widget: Any, *, title: str, title_color: str, axis_color: str, border_color: str = "#2D2D2D") -> None:
    if pg is None or Qt is None:
        return
    widget.setStyleSheet(
        f"border: 1px solid {border_color}; border-radius: 12px; background-color: #11141d;"
    )
    plot_item = widget.getPlotItem()
    plot_item.setTitle(
        f"<span style='color:{title_color}; font-size:14px; font-weight:600;'>{title}</span>"
    )
    axis_pen = pg.mkPen(border_color, width=1.1)  # type: ignore[attr-defined]
    text_pen = pg.mkPen(axis_color)  # type: ignore[attr-defined]
    for axis_name in ("left", "bottom"):
        axis = plot_item.getAxis(axis_name)
        axis.setPen(axis_pen)
        axis.setTextPen(text_pen)
    plot_item.getViewBox().setBorder(axis_pen)


class ConnectionPane(QWidget):  # type: ignore[misc]
    """Simple form for host/port selection."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "connection")
        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Connection Settings")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        host_row = QHBoxLayout()  # type: ignore[call-arg]
        host_label = QLabel("Host:")  # type: ignore[call-arg]
        self.host_edit = QLineEdit("127.0.0.1")  # type: ignore[call-arg]
        host_row.addWidget(host_label)
        host_row.addWidget(self.host_edit)

        port_row = QHBoxLayout()  # type: ignore[call-arg]
        port_label = QLabel("Port:")  # type: ignore[call-arg]
        self.port_edit = QLineEdit("9090")  # type: ignore[call-arg]
        port_row.addWidget(port_label)
        port_row.addWidget(self.port_edit)

        self.connect_button = QPushButton("Connect")  # type: ignore[call-arg]
        self.connect_button.setObjectName("connectButton")
        self.status_label = QLabel("Disconnected")  # type: ignore[call-arg]
        self.status_label.setObjectName("connectionStatus")
        self.status_label.setProperty("statusKind", "idle")
        if Qt is not None:
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]

        layout.addLayout(host_row)
        layout.addLayout(port_row)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.status_label)

        if Qt is not None and QGraphicsDropShadowEffect is not None:
            effect = QGraphicsDropShadowEffect(self)
            effect.setOffset(0, 0)
            effect.setBlurRadius(18)
            effect.setColor(QColor("#00B4FF"))
            self.connect_button.setGraphicsEffect(effect)

    def set_status(self, text: str, kind: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("statusKind", kind)
        if Qt is not None:
            # Refresh style so dynamic palette updates
            self.status_label.style().unpolish(self.status_label)  # type: ignore[attr-defined]
            self.status_label.style().polish(self.status_label)  # type: ignore[attr-defined]


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

        self.command_edit = QLineEdit(
            "python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090"
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
        self._status_locked = False
        layout.addWidget(self.command_edit)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addLayout(status_row)
        layout.addWidget(self.log_view)

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

    def append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        if running:
            self._status_locked = False
            self._set_status("Running…", "running")
            self._start_timer()
        else:
            self._stop_timer()
            if not self._status_locked:
                self._set_status("Idle", "idle")

    def indicate_stopping(self) -> None:
        self._status_locked = True
        self._set_status("Stopping…", "stopping")

    def mark_exit(self, code: int) -> None:
        self._status_locked = True
        status = "Completed" if code == 0 else f"Exited ({code})"
        state = "completed" if code == 0 else "error"
        self._set_status(status, state)
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
        if Qt is not None:
            self.status_label.style().unpolish(self.status_label)  # type: ignore[attr-defined]
            self.status_label.style().polish(self.status_label)  # type: ignore[attr-defined]

    def apply_config_path(self, path: str) -> None:
        """Update the command template and status label with ``--config`` path."""

        if not path:
            return
        try:
            resolved = str(Path(path).expanduser().resolve())
        except OSError:
            resolved = str(Path(path).expanduser())

        self.config_label.setText(f"Config: {resolved}")
        self.config_label.setProperty("statusKind", "connected")
        if Qt is not None:
            self.config_label.style().unpolish(self.config_label)  # type: ignore[attr-defined]
            self.config_label.style().polish(self.config_label)  # type: ignore[attr-defined]

        text = self.command_edit.text().strip()
        if not text:
            default_command = [
                "python",
                "hashmap_cli.py",
                "--config",
                resolved,
                "run-csv",
                "--csv",
                "data/workloads/w_uniform.csv",
            ]
            self.command_edit.setText(" ".join(shlex.quote(part) for part in default_command))
            return

        try:
            args = list(ProcessManager.parse_command(text))
        except ValueError:
            self.command_edit.setText(f"{text} --config {shlex.quote(resolved)}")
            return

        if not args:
            args = ["python", "hashmap_cli.py"]

        if "--config" in args:
            idx = args.index("--config")
            if idx == len(args) - 1:
                args.append(resolved)
            else:
                args[idx + 1] = resolved
        else:
            insert_at = len(args)
            for index, arg in enumerate(args):
                if arg.endswith("hashmap_cli.py") or arg.endswith("hashmap_cli.pyc"):
                    insert_at = index + 1
                    break
            args[insert_at:insert_at] = ["--config", resolved]

        rebuilt = " ".join(shlex.quote(part) for part in args)
        self.command_edit.setText(rebuilt)


class ConfigEditorPane(QWidget):  # type: ignore[misc]
    """Schema-driven config editor with preset management."""

    if pyqtSignal is not None:  # type: ignore[truthy-bool]
        configSaved = pyqtSignal(str)  # type: ignore[call-arg]
        configLoaded = pyqtSignal(str)  # type: ignore[call-arg]
        presetSaved = pyqtSignal(str)  # type: ignore[call-arg]
    else:  # pragma: no cover - signals only exist when Qt is available
        configSaved = None  # type: ignore[assignment]
        configLoaded = None  # type: ignore[assignment]
        presetSaved = None  # type: ignore[assignment]

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "config")
        self._field_specs: Dict[Tuple[str, ...], FieldSpec] = {spec.path: spec for spec in CONFIG_FIELDS}
        self._field_widgets: Dict[Tuple[str, ...], Any] = {}
        self._current_config = AppConfig()
        self._config_saved_callbacks: List[Callable[[str], None]] = []
        self._config_loaded_callbacks: List[Callable[[str], None]] = []
        self._preset_saved_callbacks: List[Callable[[str], None]] = []

        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Config Editor")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        path_row = QHBoxLayout()  # type: ignore[call-arg]
        path_label = QLabel("Path:")  # type: ignore[call-arg]
        self.path_edit = QLineEdit("config.toml")  # type: ignore[call-arg]
        self.path_edit.setObjectName("configPathEdit")
        self.load_button = QPushButton("Load")  # type: ignore[call-arg]
        self.save_button = QPushButton("Save")  # type: ignore[call-arg]
        path_row.addWidget(path_label)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.load_button)
        path_row.addWidget(self.save_button)
        layout.addLayout(path_row)

        self.binding_label = QLabel("Config target: config.toml")  # type: ignore[call-arg]
        self.binding_label.setObjectName("configBindingLabel")
        self.binding_label.setWordWrap(True)  # type: ignore[attr-defined]
        layout.addWidget(self.binding_label)
        self._update_binding_label("config.toml")

        self.form_layout = QFormLayout()  # type: ignore[call-arg]
        self.form_layout.setContentsMargins(4, 4, 4, 4)
        for spec in CONFIG_FIELDS:
            widget = self._create_field_widget(spec)
            if spec.help_text:
                widget.setToolTip(spec.help_text)  # type: ignore[attr-defined]
            self.form_layout.addRow(spec.prompt + ":", widget)
            self._field_widgets[spec.path] = widget
        layout.addLayout(self.form_layout)

        preset_row = QHBoxLayout()  # type: ignore[call-arg]
        preset_label = QLabel("Preset:")  # type: ignore[call-arg]
        self.preset_combo = QComboBox()  # type: ignore[call-arg]
        self.preset_combo.setObjectName("presetSelector")
        self.refresh_presets_button = QPushButton("Refresh")  # type: ignore[call-arg]
        self.apply_preset_button = QPushButton("Apply")  # type: ignore[call-arg]
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.refresh_presets_button)
        preset_row.addWidget(self.apply_preset_button)
        layout.addLayout(preset_row)

        preset_save_row = QHBoxLayout()  # type: ignore[call-arg]
        self.new_preset_edit = QLineEdit()  # type: ignore[call-arg]
        self.new_preset_edit.setPlaceholderText("Preset name")  # type: ignore[attr-defined]
        self.save_preset_button = QPushButton("Save preset")  # type: ignore[call-arg]
        preset_save_row.addWidget(self.new_preset_edit, 1)
        preset_save_row.addWidget(self.save_preset_button)
        layout.addLayout(preset_save_row)

        self.status_label = QLabel("")  # type: ignore[call-arg]
        self.status_label.setObjectName("configStatusLabel")
        self.status_label.setWordWrap(True)  # type: ignore[attr-defined]
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.load_button.clicked.connect(self._on_load_clicked)  # type: ignore[attr-defined]
        self.save_button.clicked.connect(self._on_save_clicked)  # type: ignore[attr-defined]
        self.refresh_presets_button.clicked.connect(self.refresh_presets)  # type: ignore[attr-defined]
        self.apply_preset_button.clicked.connect(self._on_apply_preset)  # type: ignore[attr-defined]
        self.save_preset_button.clicked.connect(self._on_save_preset)  # type: ignore[attr-defined]

        try:
            self.presets_dir = resolve_presets_dir(None)
        except Exception:  # pragma: no cover - fallback when preset dir cannot be prepared
            fallback = Path.cwd() / "presets"
            fallback.mkdir(parents=True, exist_ok=True)
            self.presets_dir = fallback
            self._show_status(f"Using fallback preset directory: {fallback}", error=True)

        self._populate_fields(self._current_config)
        self.refresh_presets()

    def export_config(self) -> AppConfig:
        """Return the current form as a validated AppConfig."""

        return self._collect_config()

    def refresh_presets(self) -> None:
        try:
            presets = list_presets(self.presets_dir)
        except Exception as exc:  # pragma: no cover - IO issues
            self._show_status(f"Failed to list presets: {exc}", error=True)
            return
        current = self.preset_combo.currentData() if hasattr(self.preset_combo, "currentData") else None
        self.preset_combo.clear()
        self.preset_combo.addItem("Select preset…", userData=None)  # type: ignore[attr-defined]
        for name in presets:
            display = self._format_preset_display(name)
            self.preset_combo.addItem(display, userData=name)  # type: ignore[attr-defined]
        if current:
            index = self.preset_combo.findData(current)  # type: ignore[attr-defined]
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)

    def _create_field_widget(self, spec: FieldSpec) -> Any:
        if spec.kind == "choice" and QComboBox is not None:
            widget = QComboBox()  # type: ignore[call-arg]
            for choice in spec.choices:
                widget.addItem(choice, userData=choice)  # type: ignore[attr-defined]
            return widget
        if spec.kind == "bool" and QCheckBox is not None:
            return QCheckBox()  # type: ignore[call-arg]
        line = QLineEdit()  # type: ignore[call-arg]
        if spec.kind == "optional_float":
            line.setPlaceholderText("none")  # type: ignore[attr-defined]
        return line

    def _populate_fields(self, cfg: AppConfig) -> None:
        for spec in CONFIG_FIELDS:
            widget = self._field_widgets.get(spec.path)
            if widget is None:
                continue
            value = self._get_value(cfg, spec.path)
            if isinstance(widget, QComboBox):
                index = widget.findData(value)  # type: ignore[attr-defined]
                if index < 0:
                    widget.addItem(str(value), userData=value)  # type: ignore[attr-defined]
                    index = widget.count() - 1
                widget.setCurrentIndex(index)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))  # type: ignore[attr-defined]
            elif isinstance(widget, QLineEdit):
                if value is None:
                    widget.setText("")
                elif isinstance(value, float):
                    widget.setText(self._format_float(value))
                else:
                    widget.setText(str(value))

    def _collect_config(self) -> AppConfig:
        updates: Dict[Tuple[str, ...], Any] = {}
        errors: list[str] = []
        for spec, widget in self._field_widgets.items():
            try:
                updates[spec] = self._extract_widget_value(self._field_specs[spec], widget)
            except BadInputError as exc:
                errors.append(str(exc))
        if errors:
            raise BadInputError("; ".join(errors))
        cfg = apply_updates_to_config(AppConfig(), updates)
        self._current_config = cfg
        return cfg

    def _extract_widget_value(self, spec: FieldSpec, widget: Any) -> Any:
        if isinstance(widget, QComboBox):
            data = widget.currentData()  # type: ignore[attr-defined]
            return data if data is not None else widget.currentText()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()  # type: ignore[attr-defined]
        if isinstance(widget, QLineEdit):
            text = widget.text().strip()
            if spec.kind == "int":
                if not text:
                    raise BadInputError(f"{spec.prompt} cannot be empty")
                try:
                    return int(text)
                except ValueError as exc:
                    raise BadInputError(f"{spec.prompt} must be an integer") from exc
            if spec.kind == "float":
                if not text:
                    raise BadInputError(f"{spec.prompt} cannot be empty")
                try:
                    return float(text)
                except ValueError as exc:
                    raise BadInputError(f"{spec.prompt} must be numeric") from exc
            if spec.kind == "optional_float":
                if not text:
                    return None
                lowered = text.lower()
                if lowered in {"none", "null", "off", "disabled"}:
                    return None
                try:
                    return float(text)
                except ValueError as exc:
                    raise BadInputError(f"{spec.prompt} must be numeric or 'none'") from exc
            return text
        return widget

    def _on_load_clicked(self) -> None:
        path = self._get_config_path()
        try:
            cfg = load_config_document(path.resolve())
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        except Exception as exc:  # pragma: no cover - unexpected IO errors
            self._show_status(f"Failed to load {path}: {exc}", error=True)
            return
        self._current_config = cfg
        self.path_edit.setText(str(path))
        self._populate_fields(cfg)
        self._update_binding_label(str(path))
        self._show_status(f"Loaded {path}")
        self._emit_config_loaded(str(path))

    def _on_save_clicked(self) -> None:
        try:
            cfg = self._collect_config()
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        path = self._get_config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(format_app_config_to_toml(cfg), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - IO errors
            self._show_status(f"Failed to write {path}: {exc}", error=True)
            return
        self.path_edit.setText(str(path))
        self._update_binding_label(str(path))
        self._show_status(f"Saved {path}")
        self._emit_config_saved(str(path))

    def _on_apply_preset(self) -> None:
        preset = self.preset_combo.currentData() if hasattr(self.preset_combo, "currentData") else None
        if not preset:
            self._show_status("Select a preset to apply.", error=True)
            return
        try:
            cfg = load_preset(str(preset), self.presets_dir)
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        self._current_config = cfg
        self._populate_fields(cfg)
        self._show_status(f"Applied preset '{preset}'")

    def _on_save_preset(self) -> None:
        name = self.new_preset_edit.text().strip()
        if not name:
            self._show_status("Enter a preset name.", error=True)
            return
        try:
            cfg = self._collect_config()
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        try:
            path = save_preset(cfg, name, self.presets_dir, overwrite=True)
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        self.refresh_presets()
        index = self.preset_combo.findData(path.stem)  # type: ignore[attr-defined]
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self._show_status(f"Preset saved to {path}")
        self._emit_preset_saved(str(path))

    def _get_config_path(self) -> Path:
        raw = self.path_edit.text().strip()
        if not raw:
            raw = "config.toml"
        return Path(raw).expanduser()

    @staticmethod
    def _get_value(cfg: AppConfig, path: Tuple[str, ...]) -> Any:
        node: Any = cfg
        for key in path:
            node = getattr(node, key)
        return node

    @staticmethod
    def _format_float(value: float) -> str:
        text = f"{value:.6f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    @staticmethod
    def _format_preset_display(name: str) -> str:
        pretty = name.replace("_", " ").replace("-", " ")
        return pretty.title()

    def _show_status(self, message: str, *, error: bool = False) -> None:
        color = "#FF6B6B" if error else "#00FFAA"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status_label.setText(message)

    def add_config_saved_callback(self, callback: Callable[[str], None]) -> None:
        self._config_saved_callbacks.append(callback)

    def add_config_loaded_callback(self, callback: Callable[[str], None]) -> None:
        self._config_loaded_callbacks.append(callback)

    def add_preset_saved_callback(self, callback: Callable[[str], None]) -> None:
        self._preset_saved_callbacks.append(callback)

    def _update_binding_label(self, path: str) -> None:
        self.binding_label.setText(f"Config target: {path}")

    def _emit_config_saved(self, path: str) -> None:
        if self.configSaved is not None:  # type: ignore[truthy-bool]
            try:
                self.configSaved.emit(path)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - Qt emits may fail in headless tests
                pass
        for callback in list(self._config_saved_callbacks):
            callback(path)

    def _emit_config_loaded(self, path: str) -> None:
        if self.configLoaded is not None:  # type: ignore[truthy-bool]
            try:
                self.configLoaded.emit(path)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        for callback in list(self._config_loaded_callbacks):
            callback(path)

    def _emit_preset_saved(self, path: str) -> None:
        if self.presetSaved is not None:  # type: ignore[truthy-bool]
            try:
                self.presetSaved.emit(path)  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        for callback in list(self._preset_saved_callbacks):
            callback(path)


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
        path_row.addWidget(path_label)
        path_row.addWidget(self.spec_edit, 1)
        path_row.addWidget(self.load_button)
        path_row.addWidget(self.discover_button)
        layout.addLayout(path_row)

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

        self.load_button.clicked.connect(self._on_load_clicked)  # type: ignore[attr-defined]
        self.discover_button.clicked.connect(lambda: self.refresh_specs(select_first=True))  # type: ignore[attr-defined]
        self.analyze_button.clicked.connect(self._on_analyze_clicked)  # type: ignore[attr-defined]

        self.refresh_specs(select_first=True)

    def set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        if Qt is not None:
            self.status_label.style().unpolish(self.status_label)  # type: ignore[attr-defined]
            self.status_label.style().polish(self.status_label)  # type: ignore[attr-defined]

    def refresh_specs(self, *, select_first: bool) -> None:
        """Discover example suite specs and populate the selector."""

        if self.spec_selector is None:
            return
        specs = self._discover_specs()
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
        path = self.get_spec_path()
        if path is None:
            self.set_status("Enter a spec path to load.", "error")
            return
        spec = self._load_spec(path)
        if spec is None:
            return
        self._current_spec = spec
        self._current_spec_path = path
        self._ensure_selector_entry(path)
        self._render_spec(spec, path)
        self.set_status(f"Loaded {path}", "idle")

    def _load_spec(self, path: Path) -> Optional[BatchSpec]:
        try:
            spec = load_spec(path)
        except FileNotFoundError:
            self.set_status(f"Spec not found: {path}", "error")
            return None
        except Exception as exc:
            self.set_status(f"Spec error: {exc}", "error")
            return None
        return spec

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

        self.view_combo = QComboBox() if QComboBox is not None else None  # type: ignore[call-arg]
        if self.view_combo is not None:
            self.view_combo.setObjectName("dnaViewSelector")
            for label in (
                self._VIEW_HEATMAP,
                self._VIEW_BUCKETS_ID,
                self._VIEW_BUCKETS_SORTED,
                self._VIEW_DEPTH,
            ):
                self.view_combo.addItem(label)
            self.view_combo.currentTextChanged.connect(self._on_view_changed)  # type: ignore[attr-defined]
            self.view_combo.setCurrentText(self._view_mode)
            controls.addWidget(self.view_combo)

        self.bucket_limit_spin = QSpinBox() if QSpinBox is not None else None  # type: ignore[call-arg]
        if self.bucket_limit_spin is not None:
            self.bucket_limit_spin.setObjectName("dnaBucketLimit")
            self.bucket_limit_spin.setRange(8, 512)
            self.bucket_limit_spin.setValue(self._DEFAULT_LIMIT)
            self.bucket_limit_spin.setSingleStep(8)
            self.bucket_limit_spin.valueChanged.connect(self._on_bucket_limit_changed)  # type: ignore[attr-defined]
            controls.addWidget(QLabel("Top buckets:"))  # type: ignore[call-arg]
            controls.addWidget(self.bucket_limit_spin)

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
        if Qt is not None:
            self.baseline_label.style().unpolish(self.baseline_label)  # type: ignore[attr-defined]
            self.baseline_label.style().polish(self.baseline_label)  # type: ignore[attr-defined]
        if self.compare_toggle is not None:
            self.compare_toggle.setChecked(True)
        self._render_all()

    def clear_baseline(self) -> None:
        self._baseline_result = None
        self._baseline_label = None
        self.baseline_label.setText("Baseline: none")
        self.baseline_label.setProperty("baselineSet", "false")
        if Qt is not None:
            self.baseline_label.style().unpolish(self.baseline_label)  # type: ignore[attr-defined]
            self.baseline_label.style().polish(self.baseline_label)  # type: ignore[attr-defined]
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

    def _render_all(self) -> None:
        if not self._supports_charts or self._primary_plot is None:
            return
        self._render_plot(self._primary_plot, self._current_result, self._current_label or "Primary")
        show_comparison = (
            self._baseline_result is not None
            and self.compare_toggle is not None
            and self.compare_toggle.isChecked()
            and self._comparison_plot is not None
        )
        if show_comparison:
            self._comparison_plot.show()
            self._render_plot(self._comparison_plot, self._baseline_result, self._baseline_label or "Baseline")
        elif self._comparison_plot is not None:
            self._comparison_plot.clear()
            self._comparison_plot.hide()

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
        if (
            self._primary_plot is None
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
        if (
            self._heatmap_image is None
            or self._heatmap_counts is None
            or self._heatmap_side <= 0
        ):
            return False
        plot_item = self._primary_plot.getPlotItem()
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
        QToolTip.showText(QCursor.pos(), tooltip, self._primary_plot)
        return True

    def _handle_bucket_hover(self, scene_pos: Any) -> bool:
        if self._primary_plot is None or not self._bucket_entries:
            return False
        plot_item = self._primary_plot.getPlotItem()
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
        QToolTip.showText(QCursor.pos(), tooltip, self._primary_plot)
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

class MetricsPane(QWidget):  # type: ignore[misc]
    """Displays snapshot summaries and recent events."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "metrics")
        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        heading = QLabel("Live Telemetry")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        self.summary_label = QLabel("Waiting for metrics…")  # type: ignore[call-arg]
        self.summary_label.setWordWrap(True)
        if Qt is not None:
            self.summary_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.summary_label)
        self._supports_charts = Qt is not None and pg is not None
        self._max_points = 120
        self._tick_index = 0
        self._ops_curve = None
        self._load_curve = None
        self._latency_bars = None
        self._probe_bars = None
        self._heatmap_item = None
        self._ops_x: list[float] = []
        self._ops_y: list[float] = []
        self._load_x: list[float] = []
        self._load_y: list[float] = []
        self._last_ops: Optional[float] = None
        self._last_time: Optional[float] = None
        self._last_throughput: Optional[float] = None
        self._last_wall_time: Optional[float] = None
        self._latency_plot = None
        self._probe_plot = None
        self._heatmap_plot = None
        self._latency_status = None
        self._probe_status = None
        self._heatmap_status = None
        self._heatmap_gradient = None
        self._analytics_tabs = None
        if self._supports_charts:
            tabs = QTabWidget(self) if Qt is not None and QTabWidget is not None else None  # type: ignore[call-arg]
            if tabs is not None:
                tabs.setObjectName("metricsTabs")

            self._ops_plot = pg.PlotWidget(title="Ops per second")  # type: ignore[attr-defined]
            self._ops_plot.setObjectName("opsPlot")
            self._ops_plot.showGrid(x=True, y=True, alpha=0.3)  # type: ignore[attr-defined]
            self._ops_plot.setLabel("bottom", "Snapshot", color="#8CA3AF")  # type: ignore[attr-defined]
            self._ops_plot.setLabel("left", "Ops/s", color="#00FF6C")  # type: ignore[attr-defined]
            self._ops_curve = self._ops_plot.plot(pen=pg.mkPen("#00FF6C", width=2.4))  # type: ignore[attr-defined]
            _style_plot(
                self._ops_plot,
                title="Ops per second",
                title_color="#00FF6C",
                axis_color="#8CA3AF",
            )
            if tabs is not None:
                throughput_container = QWidget(self)  # type: ignore[call-arg]
                throughput_layout = QVBoxLayout(throughput_container)  # type: ignore[call-arg]
                throughput_layout.setContentsMargins(6, 6, 6, 6)
                throughput_layout.addWidget(self._ops_plot)
                idx = tabs.addTab(throughput_container, "Throughput")  # type: ignore[attr-defined]
                tip_throughput = "Operations per second. Shows how quickly the hashmap processes requests."
                tabs.setTabToolTip(idx, tip_throughput)  # type: ignore[attr-defined]
                tabs.tabBar().setTabToolTip(idx, tip_throughput)  # type: ignore[attr-defined]
            else:
                layout.addWidget(self._ops_plot)

            self._load_plot = pg.PlotWidget(title="Load factor")  # type: ignore[attr-defined]
            self._load_plot.setObjectName("loadPlot")
            self._load_plot.showGrid(x=True, y=True, alpha=0.3)  # type: ignore[attr-defined]
            self._load_plot.setLabel("bottom", "Snapshot", color="#8CA3AF")  # type: ignore[attr-defined]
            self._load_plot.setLabel("left", "Load factor", color="#7B61FF")  # type: ignore[attr-defined]
            self._load_curve = self._load_plot.plot(pen=pg.mkPen("#7B61FF", width=2.2))  # type: ignore[attr-defined]
            self._load_plot.setYRange(0.0, 1.1, padding=0.05)  # type: ignore[attr-defined]
            _style_plot(
                self._load_plot,
                title="Load factor",
                title_color="#7B61FF",
                axis_color="#8CA3AF",
                border_color="#3A2E66",
            )
            if tabs is not None:
                load_container = QWidget(self)  # type: ignore[call-arg]
                load_layout = QVBoxLayout(load_container)  # type: ignore[call-arg]
                load_layout.setContentsMargins(6, 6, 6, 6)
                load_layout.addWidget(self._load_plot)
                idx = tabs.addTab(load_container, "Load")  # type: ignore[attr-defined]
                tip_load = "Load factor (used vs. total capacity). High load can trigger resizes or collisions."
                tabs.setTabToolTip(idx, tip_load)  # type: ignore[attr-defined]
                tabs.tabBar().setTabToolTip(idx, tip_load)  # type: ignore[attr-defined]
            else:
                layout.addWidget(self._load_plot)

            if tabs is not None:
                self._latency_plot = pg.PlotWidget(title="Latency histogram")  # type: ignore[attr-defined]
                self._latency_plot.setObjectName("latencyPlot")
                self._latency_plot.showGrid(x=True, y=True, alpha=0.25)  # type: ignore[attr-defined]
                self._latency_plot.setLabel("left", "Count", color="#F97316")  # type: ignore[attr-defined]
                self._latency_plot.setLabel("bottom", "Bucket", color="#8CA3AF")  # type: ignore[attr-defined]
                self._latency_plot.setMouseEnabled(x=False, y=False)
                self._latency_plot.setMenuEnabled(False)
                _style_plot(
                    self._latency_plot,
                    title="Latency histogram",
                    title_color="#F97316",
                    axis_color="#8CA3AF",
                    border_color="#7C2D12",
                )
                latency_container = QWidget(self)  # type: ignore[call-arg]
                latency_layout = QVBoxLayout(latency_container)  # type: ignore[call-arg]
                latency_layout.setContentsMargins(6, 6, 6, 6)
                latency_layout.addWidget(self._latency_plot)
                self._latency_status = QLabel("Waiting for histogram samples…")  # type: ignore[call-arg]
                if Qt is not None:
                    self._latency_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._latency_status.setObjectName("histStatusLabel")
                latency_layout.addWidget(self._latency_status)
                idx = tabs.addTab(latency_container, "Latency")  # type: ignore[attr-defined]
                tip_latency = "Histogram of operation response times. Highlights slow paths or spikes."
                tabs.setTabToolTip(idx, tip_latency)  # type: ignore[attr-defined]
                tabs.tabBar().setTabToolTip(idx, tip_latency)  # type: ignore[attr-defined]

                self._probe_plot = pg.PlotWidget(title="Probe distribution")  # type: ignore[attr-defined]
                self._probe_plot.setObjectName("probePlot")
                self._probe_plot.showGrid(x=True, y=True, alpha=0.25)  # type: ignore[attr-defined]
                self._probe_plot.setLabel("left", "Count", color="#0EA5E9")  # type: ignore[attr-defined]
                self._probe_plot.setLabel("bottom", "Distance", color="#8CA3AF")  # type: ignore[attr-defined]
                self._probe_plot.setMouseEnabled(x=False, y=False)
                self._probe_plot.setMenuEnabled(False)
                _style_plot(
                    self._probe_plot,
                    title="Probe distribution",
                    title_color="#0EA5E9",
                    axis_color="#8CA3AF",
                    border_color="#0F3B57",
                )
                probe_container = QWidget(self)  # type: ignore[call-arg]
                probe_layout = QVBoxLayout(probe_container)  # type: ignore[call-arg]
                probe_layout.setContentsMargins(6, 6, 6, 6)
                probe_layout.addWidget(self._probe_plot)
                self._probe_status = QLabel("Waiting for probe statistics…")  # type: ignore[call-arg]
                if Qt is not None:
                    self._probe_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._probe_status.setObjectName("histStatusLabel")
                probe_layout.addWidget(self._probe_status)
                idx = tabs.addTab(probe_container, "Probe")  # type: ignore[attr-defined]
                tip_probe = "Probe distance (collision resolution steps). Lower is better for performance."
                tabs.setTabToolTip(idx, tip_probe)  # type: ignore[attr-defined]
                tabs.tabBar().setTabToolTip(idx, tip_probe)  # type: ignore[attr-defined]

                self._heatmap_plot = pg.PlotWidget(title="Key density heatmap")  # type: ignore[attr-defined]
                self._heatmap_plot.setObjectName("heatmapPlot")
                self._heatmap_plot.setMenuEnabled(False)
                self._heatmap_plot.setMouseEnabled(x=False, y=False)
                self._heatmap_plot.hideAxis("bottom")  # type: ignore[attr-defined]
                self._heatmap_plot.hideAxis("left")  # type: ignore[attr-defined]
                self._heatmap_plot.invertY(True)  # type: ignore[attr-defined]
                self._heatmap_plot.setAspectLocked(True)  # type: ignore[attr-defined]
                _style_plot(
                    self._heatmap_plot,
                    title="Key density heatmap",
                    title_color="#38BDF8",
                    axis_color="#8CA3AF",
                    border_color="#1E3A8A",
                )
                if np is not None:
                    self._heatmap_item = pg.ImageItem()  # type: ignore[attr-defined]
                    cmap = None
                    positions = [0.0, 0.25, 0.5, 0.75, 1.0]
                    colors = [
                        (20, 11, 52),   # deep violet
                        (81, 18, 124),  # purple
                        (183, 55, 121), # magenta
                        (248, 149, 64), # orange
                        (240, 249, 33), # yellow
                    ]
                    if hasattr(pg, "colormap"):
                        try:
                            cmap = pg.colormap.ColorMap(positions, colors)  # type: ignore[attr-defined]
                            self._heatmap_item.setLookupTable(cmap.getLookupTable(alpha=False))  # type: ignore[attr-defined]
                        except Exception:
                            cmap = None
                    if cmap is not None and hasattr(pg, "GradientWidget"):
                        legend = pg.GradientWidget(orientation='bottom')  # type: ignore[attr-defined]
                        try:
                            state = {
                                'mode': 'rgb',
                                'ticks': [
                                    (p, (r, g, b, 255))
                                    for p, (r, g, b) in zip(positions, colors)
                                ],
                            }
                            legend.restoreState(state)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        legend.setMinimumHeight(22)
                        legend.setMaximumHeight(28)
                        legend.setObjectName("heatmapLegend")
                        legend.setEnabled(False)
                        self._heatmap_gradient = legend
                self._heatmap_item.setAutoDownsample(True)  # type: ignore[attr-defined]
                self._heatmap_plot.addItem(self._heatmap_item)  # type: ignore[attr-defined]
                heatmap_container = QWidget(self)  # type: ignore[call-arg]
                heatmap_layout = QVBoxLayout(heatmap_container)  # type: ignore[call-arg]
                heatmap_layout.setContentsMargins(6, 6, 6, 6)
                heatmap_layout.addWidget(self._heatmap_plot)
                self._heatmap_status = QLabel("Waiting for key-density samples…")  # type: ignore[call-arg]
                if Qt is not None:
                    self._heatmap_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._heatmap_status.setObjectName("histStatusLabel")
                heatmap_layout.addWidget(self._heatmap_status)
                if hasattr(self, "_heatmap_gradient") and self._heatmap_gradient is not None:
                    heatmap_layout.addWidget(self._heatmap_gradient)
                    label_row = QWidget(self)  # type: ignore[call-arg]
                    label_layout = QHBoxLayout(label_row)  # type: ignore[call-arg]
                    label_layout.setContentsMargins(0, 4, 0, 0)
                    min_label = QLabel("min")  # type: ignore[call-arg]
                    max_label = QLabel("max")  # type: ignore[call-arg]
                    min_label.setStyleSheet("color:#d1d9ff;font-size:11px;")
                    max_label.setStyleSheet("color:#d1d9ff;font-size:11px;")
                    label_layout.addWidget(min_label)
                    label_layout.addStretch()
                    label_layout.addWidget(max_label)
                    heatmap_layout.addWidget(label_row)
                idx = tabs.addTab(heatmap_container, "Heatmap")  # type: ignore[attr-defined]
                tip_heatmap = "Bucket density visualization. Bright spots = heavy clustering."
                tabs.setTabToolTip(idx, tip_heatmap)  # type: ignore[attr-defined]
                tabs.tabBar().setTabToolTip(idx, tip_heatmap)  # type: ignore[attr-defined]

            if tabs is not None:
                layout.addWidget(tabs)
                self._analytics_tabs = tabs
        self.events_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.events_view.setReadOnly(True)
        self.events_view.setObjectName("eventsLog")
        layout.addWidget(self.events_view)
        self.setLayout(layout)

    def update_summary(self, text: str) -> None:
        self.summary_label.setText(text)

    def update_snapshot(self, snapshot: MetricsSnapshot) -> None:
        self._tick_index += 1
        throughput = self._estimate_throughput(snapshot)
        summary = self._summarize_snapshot(snapshot, throughput)
        self.update_summary(summary)
        self._update_charts(snapshot, throughput)
        self.update_events(snapshot.events)

    def update_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            self.events_view.setPlainText("No recent events.")
            return
        lines = []
        for event in reversed(events[-20:]):
            etype = event.get("type", "event")
            backend = event.get("backend", "-")
            timestamp = event.get("t", "-")
            lines.append(f"{timestamp:.2f}s — {etype} (backend={backend})" if isinstance(timestamp, (int, float)) else f"{etype} (backend={backend})")
        self.events_view.setPlainText("\n".join(lines))

    def _summarize_snapshot(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> str:
        tick = snapshot.tick
        backend = tick.get("backend", "unknown")
        ops = tick.get("ops", 0)
        summary = f"Backend: {backend} | Ops: {ops}"
        load_factor = tick.get("load_factor")
        if isinstance(load_factor, (int, float)):
            summary += f" | Load factor: {load_factor:.3f}"
        if not isinstance(throughput, (int, float)):
            throughput = tick.get("ops_per_second_instant")
        if isinstance(throughput, (int, float)):
            summary += f" | Ops/s: {throughput:.1f}"
        latency_ms = tick.get("latency_ms")
        if isinstance(latency_ms, Mapping):
            overall = latency_ms.get("overall")
            if isinstance(overall, Mapping):
                p99 = overall.get("p99")
                if isinstance(p99, (int, float)):
                    summary += f" | p99: {p99:.3f} ms"
        return summary

    def _update_charts(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> None:
        if not self._supports_charts:
            return
        tick = snapshot.tick
        load_factor = tick.get("load_factor")
        self._append_point(self._ops_x, self._ops_y, throughput, self._ops_curve)
        self._append_point(self._load_x, self._load_y, load_factor, self._load_curve)
        self._update_latency_chart(snapshot.latency)
        self._update_probe_chart(snapshot.probe)
        self._update_heatmap(snapshot.heatmap)

    def _update_latency_chart(self, latency_payload: Mapping[str, Any]) -> None:
        if self._latency_plot is None or pg is None:
            return
        series = list(extract_latency_histogram(latency_payload, "overall"))
        if series:
            series = series[-12:]
        xs = list(range(len(series))) if series else [0]
        heights = [count for _, count in series] if series else [0]
        width = 0.8
        if self._latency_bars is None and pg is not None:
            self._latency_bars = pg.BarGraphItem(  # type: ignore[attr-defined]
                x=xs,
                height=heights,
                width=width,
                brush=pg.mkBrush("#F97316"),
                pen=pg.mkPen("#F97316"),
            )
            self._latency_plot.addItem(self._latency_bars)
        elif self._latency_bars is not None:
            self._latency_bars.setOpts(x=xs, height=heights, width=width)  # type: ignore[attr-defined]
        if self._latency_status is not None:
            self._latency_status.setVisible(not series)
        axis = self._latency_plot.getAxis("bottom")  # type: ignore[attr-defined]
        ticks = []
        for idx, (upper, _count) in enumerate(series):
            if math.isinf(upper):
                label = "≤inf"
            elif upper >= 1.0:
                label = f"≤{upper:.1f} ms"
            elif upper >= 0.1:
                label = f"≤{upper:.2f} ms"
            elif upper >= 0.01:
                label = f"≤{upper:.3f} ms"
            else:
                label = f"≤{upper * 1000:.1f} μs"
            ticks.append((idx, label))
        axis.setTicks([ticks])
        self._latency_plot.enableAutoRange(axis="y", enable=True)  # type: ignore[attr-defined]

    def _update_probe_chart(self, probe_payload: Mapping[str, Any]) -> None:
        if self._probe_plot is None or pg is None:
            return
        series = list(extract_probe_histogram(probe_payload))
        if series:
            series = series[:32]
        xs = [distance for distance, _count in series] if series else [0]
        heights = [count for _distance, count in series] if series else [0]
        width = 0.6
        if self._probe_bars is None and pg is not None:
            self._probe_bars = pg.BarGraphItem(  # type: ignore[attr-defined]
                x=xs,
                height=heights,
                width=width,
                brush=pg.mkBrush("#0EA5E9"),
                pen=pg.mkPen("#0EA5E9"),
            )
            self._probe_plot.addItem(self._probe_bars)
        elif self._probe_bars is not None:
            self._probe_bars.setOpts(x=xs, height=heights, width=width)  # type: ignore[attr-defined]
        if self._probe_status is not None:
            self._probe_status.setVisible(not series)
        axis = self._probe_plot.getAxis("bottom")  # type: ignore[attr-defined]
        if series:
            axis.setTicks([[ (distance, str(distance)) for distance in xs ]])
        else:
            axis.setTicks([])
        self._probe_plot.enableAutoRange(axis="y", enable=True)  # type: ignore[attr-defined]

    def _update_heatmap(self, heatmap_payload: Mapping[str, Any]) -> None:
        if self._heatmap_plot is None or self._heatmap_item is None or np is None:
            return
        matrix = heatmap_payload.get("matrix")
        if not isinstance(matrix, list) or not matrix:
            data = np.zeros((1, 1), dtype=float)
        else:
            try:
                data = np.array(matrix, dtype=float)
            except Exception:
                data = np.zeros((1, 1), dtype=float)
        max_value = heatmap_payload.get("max")
        if not isinstance(max_value, (int, float)) or max_value <= 0:
            try:
                max_value = float(np.max(data))
            except Exception:
                max_value = 1.0
        max_value = max(max_value, 1.0)
        self._heatmap_item.setImage(data, levels=(0.0, max_value))  # type: ignore[attr-defined]
        if self._heatmap_status is not None:
            has_data = bool(np.any(data)) if hasattr(np, "any") else True
            self._heatmap_status.setVisible(not has_data)

    def _estimate_throughput(self, snapshot: MetricsSnapshot) -> Optional[float]:
        tick = snapshot.tick
        raw = tick.get("ops_per_second") or tick.get("throughput")
        throughput: Optional[float]
        if isinstance(raw, (int, float)):
            throughput = float(raw)
        else:
            throughput = self._last_throughput

        ops = tick.get("ops")
        timestamp = tick.get("t")
        now = time.monotonic()

        ops_f = float(ops) if isinstance(ops, (int, float)) else None
        time_f = float(timestamp) if isinstance(timestamp, (int, float)) else None

        delta_ops: Optional[float] = None
        if ops_f is not None and self._last_ops is not None:
            delta_ops = ops_f - self._last_ops

        delta_time: Optional[float] = None
        if time_f is not None and self._last_time is not None:
            delta_time = time_f - self._last_time
        if (delta_time is None or delta_time <= 0.0) and self._last_wall_time is not None:
            delta_time = now - self._last_wall_time

        if (
            delta_ops is not None
            and delta_ops >= 0.0
            and delta_time is not None
            and delta_time > 0.0
        ):
            throughput = max(delta_ops / delta_time, 0.0)

        if ops_f is not None:
            self._last_ops = ops_f
        if time_f is not None:
            self._last_time = time_f
        self._last_wall_time = now
        if throughput is not None:
            self._last_throughput = throughput

        return throughput if throughput is not None else 0.0

    def _append_point(
        self,
        xs: list[float],
        ys: list[float],
        value: Any,
        curve: Any,
    ) -> None:
        if curve is None or not isinstance(value, (int, float)):
            return
        xs.append(float(self._tick_index))
        ys.append(float(value))
        if len(xs) > self._max_points:
            xs.pop(0)
            ys.pop(0)
        curve.setData(xs, ys)
