# mypy: ignore-errors
"""Shared helpers and optional imports for Mission Control widgets."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    cast,
)

QT_IMPORT_ERROR: Exception | None = None

try:  # pragma: no cover - only when PyQt6 is present
    from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QColor, QCursor
    from PyQt6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QGraphicsDropShadowEffect,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QSlider,
        QSpinBox,
        QTabWidget,
        QToolTip,
        QVBoxLayout,
        QWidget,
    )
except Exception as exc:  # pragma: no cover - CI or headless environments  # noqa: BLE001
    QT_IMPORT_ERROR = exc
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
    QProgressBar = cast(Any, None)
    QFileDialog = cast(Any, None)
    QSlider = cast(Any, None)
    QDoubleSpinBox = cast(Any, None)
    pyqtSignal = None  # type: ignore[assignment]  # noqa: N816
    QColor = cast(Any, object)
    QCursor = cast(Any, object)
    QTimer = cast(Any, None)
    Qt = None  # type: ignore[assignment]
    QObject = cast(Any, object)

try:  # pragma: no cover - optional plotting dependency
    import pyqtgraph as pg  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - charting optional  # noqa: BLE001
    pg = cast(Any, None)
else:  # pragma: no cover - requires PyQtGraph
    pg.setConfigOption("background", "#121212")
    pg.setConfigOption("foreground", "#EEEEEE")
    pg.setConfigOptions(antialias=True)

try:  # pragma: no cover - numpy optional at runtime but bundled with pyqtgraph
    import numpy as np  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback when numpy missing  # noqa: BLE001
    np = cast(Any, None)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..metrics_client import MetricsSnapshot  # noqa: F401


__all__ = [
    "Qt",
    "QTimer",
    "pyqtSignal",
    "QLabel",
    "QLineEdit",
    "QPushButton",
    "QVBoxLayout",
    "QWidget",
    "QHBoxLayout",
    "QPlainTextEdit",
    "QGraphicsDropShadowEffect",
    "QTabWidget",
    "QFormLayout",
    "QComboBox",
    "QCheckBox",
    "QSpinBox",
    "QToolTip",
    "QProgressBar",
    "QFileDialog",
    "QSlider",
    "QDoubleSpinBox",
    "QColor",
    "QCursor",
    "pg",
    "np",
    "QObject",
    "QT_IMPORT_ERROR",
    "_safe_int",
    "_safe_float",
    "extract_latency_histogram",
    "extract_probe_histogram",
    "style_plot",
]


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
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
) -> Sequence[tuple[float, int]]:
    """Return per-bucket counts from a cumulative latency histogram payload."""

    operations = payload.get("operations")
    if not isinstance(operations, Mapping):
        return []
    raw_series = operations.get(series)
    if not isinstance(raw_series, Iterable):
        return []

    buckets: list[tuple[float, int]] = []
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


def extract_probe_histogram(payload: Mapping[str, Any]) -> Sequence[tuple[int, int]]:
    """Normalise probe histogram payload to (distance, count) tuples."""

    buckets = payload.get("buckets")
    if not isinstance(buckets, Iterable):
        return []
    output: list[tuple[int, int]] = []
    for entry in buckets:
        distance: int | None = None
        count: int | None = None
        if isinstance(entry, Mapping):
            distance = _safe_int(entry.get("distance"))
            count = _safe_int(entry.get("count"))
        elif isinstance(entry, list | tuple) and len(entry) == 2:
            distance = _safe_int(entry[0])
            count = _safe_int(entry[1])
        if distance is None or count is None:
            continue
        output.append((distance, count))
    return output


def style_plot(
    widget: Any,
    *,
    title: str,
    title_color: str,
    axis_color: str,
    border_color: str = "#2D2D2D",
) -> None:
    """Apply a consistent dark theme to a pyqtgraph PlotWidget."""

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
