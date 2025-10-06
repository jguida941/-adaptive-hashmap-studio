"""Metrics telemetry pane."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any, Mapping, Optional

from .common import (
    QLabel,
    QHBoxLayout,
    QPlainTextEdit,
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
