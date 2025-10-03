# mypy: ignore-errors
"""Reusable PyQt6 widgets for Mission Control."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional, cast

if TYPE_CHECKING:  # pragma: no cover - typing-only import
    from .metrics_client import MetricsSnapshot

_QT_IMPORT_ERROR: Optional[Exception] = None

try:  # pragma: no cover - only when PyQt6 is present
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import (
        QLabel,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
        QHBoxLayout,
        QGroupBox,
        QPlainTextEdit,
    )
except Exception as exc:  # pragma: no cover - CI or headless environments
    _QT_IMPORT_ERROR = exc
    QLabel = cast(Any, object)
    QLineEdit = cast(Any, object)
    QPushButton = cast(Any, object)
    QWidget = cast(Any, object)
    QVBoxLayout = cast(Any, object)
    QHBoxLayout = cast(Any, object)
    QGroupBox = cast(Any, object)
    QPlainTextEdit = cast(Any, object)
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

__all__ = [
    "ConnectionPane",
    "RunControlPane",
    "MetricsPane",
]


class ConnectionPane(QGroupBox):  # type: ignore[misc]
    """Simple form for host/port selection."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__("Connection Settings", parent)  # type: ignore[call-arg]
        layout = QVBoxLayout()  # type: ignore[call-arg]

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
        self.status_label = QLabel("Disconnected")  # type: ignore[call-arg]
        self.status_label.setObjectName("connectionStatus")
        self.status_label.setProperty("statusKind", "idle")
        if Qt is not None:
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)  # type: ignore[attr-defined]

        layout.addLayout(host_row)
        layout.addLayout(port_row)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def set_status(self, text: str, kind: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("statusKind", kind)
        if Qt is not None:
            # Refresh style so dynamic palette updates
            self.status_label.style().unpolish(self.status_label)  # type: ignore[attr-defined]
            self.status_label.style().polish(self.status_label)  # type: ignore[attr-defined]


class RunControlPane(QGroupBox):  # type: ignore[misc]
    """Controls for launching run-csv commands."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__("Run Command", parent)  # type: ignore[call-arg]
        layout = QVBoxLayout()  # type: ignore[call-arg]
        self.command_edit = QLineEdit(
            "python hashmap_cli.py --mode adaptive run-csv --csv data/workloads/w_uniform.csv --metrics-port 9090"
        )  # type: ignore[call-arg]
        self.start_button = QPushButton("Start run-csv")  # type: ignore[call-arg]
        self.stop_button = QPushButton("Stop")  # type: ignore[call-arg]
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
        self.setLayout(layout)

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


class MetricsPane(QGroupBox):  # type: ignore[misc]
    """Displays snapshot summaries and recent events."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__("Live Telemetry", parent)  # type: ignore[call-arg]
        layout = QVBoxLayout()  # type: ignore[call-arg]
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
        self._ops_x: list[float] = []
        self._ops_y: list[float] = []
        self._load_x: list[float] = []
        self._load_y: list[float] = []
        self._last_ops: Optional[float] = None
        self._last_time: Optional[float] = None
        self._last_throughput: Optional[float] = None
        if self._supports_charts:
            self._ops_plot = pg.PlotWidget(title="Ops per second")  # type: ignore[attr-defined]
            self._ops_plot.showGrid(x=True, y=True, alpha=0.3)  # type: ignore[attr-defined]
            self._ops_plot.setLabel("bottom", "Snapshot")  # type: ignore[attr-defined]
            self._ops_plot.setLabel("left", "Ops/s")  # type: ignore[attr-defined]
            self._ops_curve = self._ops_plot.plot(pen=pg.mkPen("#00FFAA", width=2))  # type: ignore[attr-defined]
            layout.addWidget(self._ops_plot)

            self._load_plot = pg.PlotWidget(title="Load factor")  # type: ignore[attr-defined]
            self._load_plot.showGrid(x=True, y=True, alpha=0.3)  # type: ignore[attr-defined]
            self._load_plot.setLabel("bottom", "Snapshot")  # type: ignore[attr-defined]
            self._load_plot.setLabel("left", "Load factor")  # type: ignore[attr-defined]
            self._load_curve = self._load_plot.plot(pen=pg.mkPen("#7B61FF", width=2))  # type: ignore[attr-defined]
            self._load_plot.setYRange(0.0, 1.1, padding=0.05)  # type: ignore[attr-defined]
            layout.addWidget(self._load_plot)
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
        if isinstance(throughput, (int, float)):
            summary += f" | Ops/s: {throughput:.1f}"
        return summary

    def _update_charts(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> None:
        if not self._supports_charts:
            return
        tick = snapshot.tick
        load_factor = tick.get("load_factor")
        self._append_point(self._ops_x, self._ops_y, throughput, self._ops_curve)
        self._append_point(self._load_x, self._load_y, load_factor, self._load_curve)

    def _estimate_throughput(self, snapshot: MetricsSnapshot) -> Optional[float]:
        tick = snapshot.tick
        raw = tick.get("ops_per_second") or tick.get("throughput")
        if isinstance(raw, (int, float)):
            self._last_throughput = float(raw)
        ops = tick.get("ops")
        timestamp = tick.get("t")
        throughput: Optional[float] = self._last_throughput
        if isinstance(ops, (int, float)) and isinstance(timestamp, (int, float)):
            ops_f = float(ops)
            time_f = float(timestamp)
            if self._last_ops is not None and self._last_time is not None:
                delta_ops = ops_f - self._last_ops
                delta_time = time_f - self._last_time
                if delta_time > 0:
                    throughput = max(delta_ops / delta_time, 0.0)
                    self._last_throughput = throughput
            self._last_ops = ops_f
            self._last_time = time_f
        return throughput

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
