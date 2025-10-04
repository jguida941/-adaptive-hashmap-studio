# mypy: ignore-errors
"""Layout helpers for Mission Control."""

from __future__ import annotations

from typing import Optional, Any, cast

_QT_IMPORT_ERROR: Optional[Exception] = None

try:  # pragma: no cover - only when PyQt6 is available
    from PyQt6.QtWidgets import QDockWidget, QWidget, QHBoxLayout, QLabel  # type: ignore[import-not-found]
    from PyQt6.QtCore import Qt  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover
    _QT_IMPORT_ERROR = exc
    QDockWidget = cast(Any, object)
    QWidget = cast(Any, object)
    QHBoxLayout = cast(Any, object)
    QLabel = cast(Any, object)
    Qt = None  # type: ignore[assignment]


def _build_title_bar(title: str, dock: QDockWidget) -> QWidget:
    bar = QWidget(dock)
    bar.setObjectName("dockTitleBar")
    layout = QHBoxLayout(bar)  # type: ignore[call-arg]
    layout.setContentsMargins(10, 4, 10, 4)
    layout.setSpacing(4)
    grip = QLabel(":::", bar)  # type: ignore[call-arg]
    grip.setObjectName("dockGrip")
    grip.setToolTip(title)
    layout.addWidget(grip)
    layout.addStretch()
    return bar


def create_dock(title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:  # type: ignore[misc]
    dock = QDockWidget("", widget.parent())  # type: ignore[call-arg]
    dock.setObjectName(f"dock_{title.lower().replace(' ', '_')}")
    dock.setWindowTitle(title)
    if Qt is not None:
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)  # type: ignore[attr-defined]
        dock.setTitleBarWidget(_build_title_bar(title, dock))
    dock.setWidget(widget)
    return dock
