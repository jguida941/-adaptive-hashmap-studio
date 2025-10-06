"""Metrics telemetry pane."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .common import (
    QFileDialog,
    QLabel,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    Qt,
    QVBoxLayout,
    QWidget,
    extract_latency_histogram,
    extract_probe_histogram,
    np,
    pg,
    style_plot,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..metrics_client import MetricsSnapshot

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

        self._history: List["MetricsSnapshot"] = []
        self._history_throughput: List[Optional[float]] = []
        self._history_slider = (
            QSlider(Qt.Orientation.Horizontal) if Qt is not None and QSlider is not None else None  # type: ignore[call-arg]
        )
        self._history_label = QLabel("No samples yet")  # type: ignore[call-arg]
        self._history_label.setObjectName("historyStatusLabel")
        if Qt is not None:
            self._history_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._latency_series_selector = QComboBox() if QComboBox is not None else None  # type: ignore[call-arg]
        self._latency_metric_selector = QComboBox() if QComboBox is not None else None  # type: ignore[call-arg]
        self._export_button = QPushButton("Export history") if QPushButton is not None else None  # type: ignore[call-arg]
        self._accumulate_checkbox = QCheckBox("Keep history between runs") if QCheckBox is not None else None  # type: ignore[call-arg]
        if self._accumulate_checkbox is not None:
            self._accumulate_checkbox.setChecked(False)

        controls_row = QHBoxLayout()  # type: ignore[call-arg]
        controls_row.setContentsMargins(4, 0, 4, 0)
        if self._history_slider is not None:
            self._history_slider.setMinimum(1)
            self._history_slider.setMaximum(1)
            self._history_slider.setValue(1)
            self._history_slider.setEnabled(False)
            controls_row.addWidget(QLabel("History:"))  # type: ignore[call-arg]
            controls_row.addWidget(self._history_slider, 1)
        else:
            controls_row.addStretch()
        controls_row.addWidget(self._history_label)
        if self._latency_series_selector is not None and self._latency_metric_selector is not None:
            self._latency_series_selector.addItems(["overall", "put", "get", "del"])
            self._latency_metric_selector.addItems(["p50", "p90", "p99"])
            controls_row.addWidget(QLabel("Series:"))  # type: ignore[call-arg]
            controls_row.addWidget(self._latency_series_selector)
            controls_row.addWidget(QLabel("Metric:"))  # type: ignore[call-arg]
            controls_row.addWidget(self._latency_metric_selector)
        if self._export_button is not None:
            controls_row.addWidget(self._export_button)
        if self._accumulate_checkbox is not None:
            controls_row.addWidget(self._accumulate_checkbox)
        controls_row.addStretch()
        layout.addLayout(controls_row)

        if self._history_slider is not None:
            self._history_slider.valueChanged.connect(self._on_history_slider_changed)  # type: ignore[attr-defined]
        if self._latency_series_selector is not None:
            self._latency_series_selector.currentTextChanged.connect(self._on_latency_selector_changed)  # type: ignore[attr-defined]
        if self._latency_metric_selector is not None:
            self._latency_metric_selector.currentTextChanged.connect(self._on_latency_selector_changed)  # type: ignore[attr-defined]
        if self._export_button is not None:
            self._export_button.clicked.connect(self._export_history)  # type: ignore[attr-defined]
        if self._accumulate_checkbox is not None:
            self._accumulate_checkbox.toggled.connect(self._on_accumulate_toggled)  # type: ignore[attr-defined]
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
        self._scatter_plot = None
        self._scatter_item = None
        self._fft_plot = None
        self._fft_curve = None
        self._fft_status = None
        self._analytics_tabs = None
        if self._supports_charts:
            tabs = QTabWidget(self) if Qt is not None and QTabWidget is not None else None  # type: ignore[call-arg]
            if tabs is not None:
                tabs.setObjectName("metricsTabs")

                def _set_tab_tooltip(index: int, text: str) -> None:
                    tabs.setTabToolTip(index, text)  # type: ignore[attr-defined]
                    tab_bar_factory = getattr(tabs, "tabBar", None)
                    if callable(tab_bar_factory):
                        tab_bar = tab_bar_factory()
                        if tab_bar is not None:
                            tab_bar.setTabToolTip(index, text)  # type: ignore[attr-defined]

            self._ops_plot = pg.PlotWidget(title="Ops per second")  # type: ignore[attr-defined]
            self._ops_plot.setObjectName("opsPlot")
            self._ops_plot.showGrid(x=True, y=True, alpha=0.3)  # type: ignore[attr-defined]
            self._ops_plot.setLabel("bottom", "Snapshot", color="#8CA3AF")  # type: ignore[attr-defined]
            self._ops_plot.setLabel("left", "Ops/s", color="#00FF6C")  # type: ignore[attr-defined]
            self._ops_curve = self._ops_plot.plot(pen=pg.mkPen("#00FF6C", width=2.4))  # type: ignore[attr-defined]
            style_plot(
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
                _set_tab_tooltip(idx, tip_throughput)
            else:
                layout.addWidget(self._ops_plot)

            self._load_plot = pg.PlotWidget(title="Load factor")  # type: ignore[attr-defined]
            self._load_plot.setObjectName("loadPlot")
            self._load_plot.showGrid(x=True, y=True, alpha=0.3)  # type: ignore[attr-defined]
            self._load_plot.setLabel("bottom", "Snapshot", color="#8CA3AF")  # type: ignore[attr-defined]
            self._load_plot.setLabel("left", "Load factor", color="#7B61FF")  # type: ignore[attr-defined]
            self._load_curve = self._load_plot.plot(pen=pg.mkPen("#7B61FF", width=2.2))  # type: ignore[attr-defined]
            self._load_plot.setYRange(0.0, 1.1, padding=0.05)  # type: ignore[attr-defined]
            style_plot(
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
                _set_tab_tooltip(idx, tip_load)
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
                style_plot(
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
                _set_tab_tooltip(idx, tip_latency)

                self._probe_plot = pg.PlotWidget(title="Probe distribution")  # type: ignore[attr-defined]
                self._probe_plot.setObjectName("probePlot")
                self._probe_plot.showGrid(x=True, y=True, alpha=0.25)  # type: ignore[attr-defined]
                self._probe_plot.setLabel("left", "Count", color="#0EA5E9")  # type: ignore[attr-defined]
                self._probe_plot.setLabel("bottom", "Distance", color="#8CA3AF")  # type: ignore[attr-defined]
                self._probe_plot.setMouseEnabled(x=False, y=False)
                self._probe_plot.setMenuEnabled(False)
                style_plot(
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
                _set_tab_tooltip(idx, tip_probe)

                self._heatmap_plot = pg.PlotWidget(title="Key density heatmap")  # type: ignore[attr-defined]
                self._heatmap_plot.setObjectName("heatmapPlot")
                self._heatmap_plot.setMenuEnabled(False)
                self._heatmap_plot.setMouseEnabled(x=False, y=False)
                self._heatmap_plot.hideAxis("bottom")  # type: ignore[attr-defined]
                self._heatmap_plot.hideAxis("left")  # type: ignore[attr-defined]
                self._heatmap_plot.invertY(True)  # type: ignore[attr-defined]
                self._heatmap_plot.setAspectLocked(True)  # type: ignore[attr-defined]
                style_plot(
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
                _set_tab_tooltip(idx, tip_heatmap)

                if pg is not None:
                    analytics_container = QWidget(self)  # type: ignore[call-arg]
                    analytics_layout = QVBoxLayout(analytics_container)  # type: ignore[call-arg]
                    analytics_layout.setContentsMargins(6, 6, 6, 6)

                    self._scatter_plot = pg.PlotWidget(title="Load factor vs throughput")  # type: ignore[attr-defined]
                    self._scatter_plot.setObjectName("analyticsScatter")
                    self._scatter_plot.showGrid(x=True, y=True, alpha=0.2)  # type: ignore[attr-defined]
                    self._scatter_plot.setLabel("bottom", "Load factor", color="#8CA3AF")  # type: ignore[attr-defined]
                    self._scatter_plot.setLabel("left", "Ops/s", color="#A855F7")  # type: ignore[attr-defined]
                    style_plot(
                        self._scatter_plot,
                        title="Load factor vs throughput",
                        title_color="#A855F7",
                        axis_color="#8CA3AF",
                        border_color="#3B0764",
                    )
                    self._scatter_item = pg.ScatterPlotItem(size=8, brush=pg.mkBrush("#A855F7"), pen=pg.mkPen(None))  # type: ignore[attr-defined]
                    self._scatter_plot.addItem(self._scatter_item)
                    analytics_layout.addWidget(self._scatter_plot)

                    self._fft_plot = pg.PlotWidget(title="Latency FFT magnitude")  # type: ignore[attr-defined]
                    self._fft_plot.setObjectName("analyticsFft")
                    self._fft_plot.showGrid(x=True, y=True, alpha=0.2)  # type: ignore[attr-defined]
                    self._fft_plot.setLabel("bottom", "Normalised frequency", color="#8CA3AF")  # type: ignore[attr-defined]
                    self._fft_plot.setLabel("left", "Magnitude", color="#FB7185")  # type: ignore[attr-defined]
                    style_plot(
                        self._fft_plot,
                        title="Latency FFT magnitude",
                        title_color="#FB7185",
                        axis_color="#8CA3AF",
                        border_color="#7F1D1D",
                    )
                    self._fft_curve = self._fft_plot.plot(pen=pg.mkPen("#FB7185", width=2.0))  # type: ignore[attr-defined]
                    analytics_layout.addWidget(self._fft_plot)

                    self._fft_status = QLabel("Collecting samples for FFT…")  # type: ignore[call-arg]
                    if Qt is not None:
                        self._fft_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._fft_status.setObjectName("histStatusLabel")
                    analytics_layout.addWidget(self._fft_status)

                    idx = tabs.addTab(analytics_container, "Analytics")  # type: ignore[attr-defined]
                    tip_analytics = "Advanced analytics: scatter plots and latency FFT for deeper diagnostics."
                    _set_tab_tooltip(idx, tip_analytics)

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
        self._update_charts(snapshot, throughput)

        was_replay = self._in_replay_mode()
        self._append_history(snapshot, throughput)
        self._refresh_history_slider(preserve_position=was_replay)

        display_index = self._current_history_index()
        display_snapshot = self._history[display_index]
        self.update_events(display_snapshot.events)
        self._refresh_summary_for_current_tick()
        self._update_history_label()
        self._update_analytics_panels()

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

    # ------------------------------------------------------------------
    def _append_history(self, snapshot: "MetricsSnapshot", throughput: Optional[float]) -> None:
        self._history.append(snapshot)
        self._history_throughput.append(throughput)
        if len(self._history) > self._max_points:
            self._history.pop(0)
            self._history_throughput.pop(0)

    def _current_history_index(self) -> int:
        if not self._history:
            return 0
        if self._history_slider is None or not self._history_slider.isEnabled():
            return len(self._history) - 1
        value = self._history_slider.value()
        return max(1, min(value, len(self._history))) - 1

    def _in_replay_mode(self) -> bool:
        if self._history_slider is None or not self._history or not self._history_slider.isEnabled():
            return False
        return self._history_slider.value() < self._history_slider.maximum()

    def _refresh_history_slider(self, *, preserve_position: bool) -> None:
        if self._history_slider is None:
            return
        length = len(self._history)
        self._history_slider.blockSignals(True)
        if length <= 1:
            self._history_slider.setEnabled(False)
            self._history_slider.setMaximum(1)
            self._history_slider.setMinimum(1)
            self._history_slider.setValue(1)
        else:
            previous_value = self._history_slider.value()
            self._history_slider.setEnabled(True)
            self._history_slider.setMinimum(1)
            self._history_slider.setMaximum(length)
            target = previous_value if preserve_position and previous_value <= length else length
            target = max(1, min(target, length))
            self._history_slider.setValue(target)
        self._history_slider.blockSignals(False)

    def _update_history_label(self) -> None:
        if self._history_label is None:
            return
        if not self._history:
            self._history_label.setText("No samples yet")
            return
        if not self._in_replay_mode():
            self._history_label.setText("Live view")
        else:
            index = self._current_history_index() + 1
            self._history_label.setText(f"Historical tick {index}/{len(self._history)}")

    def _on_history_slider_changed(self, _value: int) -> None:
        if not self._history:
            return
        index = self._current_history_index()
        snapshot = self._history[index]
        self.update_events(snapshot.events)
        self._refresh_summary_for_current_tick()
        self._update_history_label()
        self._update_analytics_panels()

    def _current_latency_selection(self) -> Tuple[str, str]:
        series = "overall"
        metric = "p99"
        if self._latency_series_selector is not None:
            text = self._latency_series_selector.currentText()
            if text:
                series = text
        if self._latency_metric_selector is not None:
            text = self._latency_metric_selector.currentText()
            if text:
                metric = text
        return series, metric

    def _refresh_summary_for_current_tick(self) -> None:
        if not self._history:
            self.update_summary("Waiting for metrics…")
            return
        index = self._current_history_index()
        snapshot = self._history[index]
        throughput = self._history_throughput[index]
        summary = self._summarize_snapshot(snapshot, throughput)
        self.update_summary(summary)

    def _on_latency_selector_changed(self, _text: str) -> None:
        self._refresh_summary_for_current_tick()
        self._update_analytics_panels()

    def _update_analytics_panels(self) -> None:
        if not self._history:
            if self._scatter_item is not None:
                self._scatter_item.setData([])
            if self._fft_curve is not None:
                self._fft_curve.setData([], [])
            if self._fft_status is not None:
                self._fft_status.setVisible(True)
            if self._fft_plot is not None:
                self._fft_plot.setTitle("Latency FFT magnitude")  # type: ignore[attr-defined]
                self._fft_plot.setLabel("bottom", "Normalised frequency", color="#8CA3AF")  # type: ignore[attr-defined]
            return

        series, metric = self._current_latency_selection()

        if self._scatter_item is not None:
            xs: List[float] = []
            ys: List[float] = []
            for snapshot, throughput in zip(self._history, self._history_throughput):
                if throughput is None:
                    continue
                load = snapshot.tick.get("load_factor") if isinstance(snapshot.tick, Mapping) else None
                if isinstance(load, (int, float)):
                    xs.append(float(load))
                    ys.append(float(throughput))
            self._scatter_item.setData(x=xs, y=ys)

        if self._fft_curve is not None and np is not None:
            if self._fft_plot is not None:
                metric_label = metric.upper()
                self._fft_plot.setTitle(
                    f"Latency FFT – {series} / {metric_label}"
                )  # type: ignore[attr-defined]
                self._fft_plot.setLabel(
                    "bottom",
                    f"Normalised frequency ({series})",
                    color="#8CA3AF",
                )  # type: ignore[attr-defined]

            values: List[float] = []
            for snapshot in self._history:
                packet = snapshot.tick.get("latency_ms") if isinstance(snapshot.tick, Mapping) else None
                if isinstance(packet, Mapping):
                    series_payload = packet.get(series)
                    if isinstance(series_payload, Mapping):
                        raw = series_payload.get(metric)
                        if isinstance(raw, (int, float)):
                            values.append(float(raw))

            if len(values) >= 4:
                arr = np.array(values, dtype=float)
                arr = arr - np.mean(arr)
                spectrum = np.abs(np.fft.rfft(arr))
                freqs = np.fft.rfftfreq(len(arr))
                if len(freqs) > 1:
                    self._fft_curve.setData(freqs[1:], spectrum[1:])  # drop DC component
                else:
                    self._fft_curve.setData([], [])
                if self._fft_status is not None:
                    self._fft_status.setVisible(False)
            else:
                self._fft_curve.setData([], [])
                if self._fft_status is not None:
                    self._fft_status.setVisible(True)

    def _export_history(self) -> None:
        if not self._history:
            self.events_view.appendPlainText("No history samples to export.")
            return
        if QFileDialog is None:
            self.events_view.appendPlainText("Export unavailable: Qt file dialog missing.")
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export metrics history",
            "metrics_history.json",
            "JSON files (*.json);;All files (*)",
        )  # type: ignore[call-arg]
        if not filename:
            return
        payload: List[Dict[str, Any]] = []
        for snapshot, throughput in zip(self._history, self._history_throughput):
            payload.append(
                {
                    "tick": snapshot.tick,
                    "latency": snapshot.latency,
                    "probe": snapshot.probe,
                    "heatmap": snapshot.heatmap,
                    "events": snapshot.events,
                    "throughput": throughput,
                }
            )
        try:
            Path(filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover - defensive
            self.events_view.appendPlainText(f"Failed to export history: {exc}")
            return
        self.events_view.appendPlainText(f"Exported {len(payload)} samples to {filename}")

    def prepare_for_new_run(self) -> None:
        if not self._should_accumulate_history():
            self._clear_history()

    def _should_accumulate_history(self) -> bool:
        if self._accumulate_checkbox is None:
            return False
        return bool(self._accumulate_checkbox.isChecked())

    def _on_accumulate_toggled(self, checked: bool) -> None:
        if not checked:
            self._clear_history()
        else:
            self._update_history_label()
            self._refresh_summary_for_current_tick()
            self._update_analytics_panels()

    def _clear_history(self) -> None:
        self._history.clear()
        self._history_throughput.clear()
        self._tick_index = 0
        self._last_ops = None
        self._last_time = None
        self._last_throughput = None
        self._last_wall_time = None
        self._ops_x.clear()
        self._ops_y.clear()
        self._load_x.clear()
        self._load_y.clear()

        if self._history_slider is not None:
            self._history_slider.blockSignals(True)
            self._history_slider.setEnabled(False)
            self._history_slider.setMinimum(1)
            self._history_slider.setMaximum(1)
            self._history_slider.setValue(1)
            self._history_slider.blockSignals(False)

        if self._ops_curve is not None:
            self._ops_curve.setData([], [])
        if self._load_curve is not None:
            self._load_curve.setData([], [])
        if self._latency_plot is not None:
            self._latency_plot.clear()
            self._latency_bars = None
            if self._latency_status is not None:
                self._latency_status.setVisible(True)
        if self._probe_plot is not None:
            self._probe_plot.clear()
            self._probe_bars = None
            if self._probe_status is not None:
                self._probe_status.setVisible(True)
        if self._heatmap_item is not None and np is not None:
            self._heatmap_item.setImage(np.zeros((1, 1)))  # type: ignore[attr-defined]
            if self._heatmap_status is not None:
                self._heatmap_status.setVisible(True)
        if self._scatter_item is not None:
            self._scatter_item.setData([])
        if self._fft_curve is not None:
            self._fft_curve.setData([], [])
        if self._fft_status is not None:
            self._fft_status.setVisible(True)

        self.update_events([])
        self.update_summary("Waiting for metrics…")
        self._update_history_label()
        self._update_analytics_panels()

    @staticmethod
    def _first_numeric(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _summarize_snapshot(self, snapshot: MetricsSnapshot, throughput: Optional[float]) -> str:
        tick = snapshot.tick
        backend = tick.get("backend", "unknown")
        ops = tick.get("ops", 0)
        segments: List[str] = [f"Backend: {backend}", f"Ops: {ops:,}"]

        load_factor = tick.get("load_factor")
        if isinstance(load_factor, (int, float)):
            segments.append(f"Load factor: {float(load_factor):.3f}")
        else:
            segments.append("Load factor: —")

        display_throughput = throughput
        if not isinstance(display_throughput, (int, float)):
            display_throughput = self._first_numeric(
                tick,
                ("ops_per_second_instant", "ops_per_second"),
            )
        if isinstance(display_throughput, (int, float)):
            segments.append(f"Ops/s: {display_throughput:,.1f}")
        else:
            segments.append("Ops/s: —")

        series, metric = self._current_latency_selection()
        latency_value = None
        latency_ms = tick.get("latency_ms")
        if isinstance(latency_ms, Mapping):
            series_payload = latency_ms.get(series)
            if isinstance(series_payload, Mapping):
                raw = series_payload.get(metric)
                if isinstance(raw, (int, float)):
                    latency_value = float(raw)
        metric_label = metric.upper()
        if latency_value is not None:
            segments.append(f"Latency ({series} {metric_label}): {latency_value:.3f} ms")
        else:
            segments.append(f"Latency ({series} {metric_label}): —")

        return " | ".join(segments)

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
        rows, cols = data.shape if data.ndim == 2 else (len(data), len(data[0]) if len(data) else 0)
        view_box = self._heatmap_plot.getViewBox()
        if view_box is not None:
            view_box.setLimits(xMin=0.0, xMax=max(cols, 1), yMin=0.0, yMax=max(rows, 1))  # type: ignore[attr-defined]
            view_box.setRange(xRange=(0, max(cols, 1)), yRange=(0, max(rows, 1)), padding=0.0)  # type: ignore[attr-defined]
        if self._heatmap_status is not None:
            has_data = bool(np.any(data)) if hasattr(np, "any") else True
            self._heatmap_status.setVisible(not has_data)

    def _estimate_throughput(self, snapshot: MetricsSnapshot) -> Optional[float]:
        tick = snapshot.tick
        throughput: Optional[float] = self._first_numeric(
            tick,
            ("ops_per_second", "throughput", "ops_per_second_instant"),
        )
        if throughput is None:
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
