"""Workload DNA visualization pane."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, List, Optional, Tuple

from adhash.workloads import WorkloadDNAResult, format_workload_dna

from .common import (
    QColor,
    QCheckBox,
    QComboBox,
    QCursor,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QToolTip,
    Qt,
    QVBoxLayout,
    QWidget,
    np,
    pg,
)


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
        self.bucket_limit_spin = None

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
        if self.bucket_limit_spin is not None:
            self.bucket_limit_spin.setEnabled(
                mode in {self._VIEW_BUCKETS_ID, self._VIEW_BUCKETS_SORTED}
            )
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

    def _render_plot(
        self, plot: Optional[pg.PlotWidget], result: Optional[WorkloadDNAResult], title: str
    ) -> None:
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
        plot.autoRange()  # type: ignore[attr-defined]

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

        img = pg.ImageItem(grid)
        img.setLookupTable(cmap.getLookupTable())
        img.setLevels((0.0, max(clip_value, max_value, 1.0)))
        plot.addItem(img)
        plot.invertY(True)  # type: ignore[attr-defined]
        plot.setAspectLocked(True, ratio=1)
        plot.hideAxis("bottom")  # type: ignore[attr-defined]
        plot.hideAxis("left")  # type: ignore[attr-defined]
        plot_item = plot.getPlotItem()
        if plot_item is not None:
            view_box = plot_item.getViewBox()
            if view_box is not None:
                view_box.setLimits(xMin=0.0, yMin=0.0)  # type: ignore[attr-defined]
                view_box.setRange(xRange=(0, side), yRange=(0, side), padding=0.0)  # type: ignore[attr-defined]
            else:
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
        if primary_plot is None or QToolTip is None or Qt is None or pg is None:
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
        if self._heatmap_image is None or self._heatmap_counts is None or self._heatmap_side <= 0:
            return False
        primary_plot = self._primary_plot
        if primary_plot is None:
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
        orig_index = row * self._heatmap_side + column
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
