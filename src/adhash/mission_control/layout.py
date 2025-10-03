# mypy: ignore-errors
"""Layout helpers for Mission Control."""

from __future__ import annotations

from typing import Optional, Any, cast

_QT_IMPORT_ERROR: Optional[Exception] = None

try:  # pragma: no cover - only when PyQt6 is available
    from PyQt6.QtWidgets import QDockWidget, QWidget  # type: ignore[import-not-found]
    from PyQt6.QtCore import Qt  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover
    _QT_IMPORT_ERROR = exc
    QDockWidget = cast(Any, object)
    QWidget = cast(Any, object)
    Qt = None  # type: ignore[assignment]


def create_dock(title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:  # type: ignore[misc]
    dock = QDockWidget(title)  # type: ignore[call-arg]
    if Qt is not None:
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
    dock.setWidget(widget)
    return dock

