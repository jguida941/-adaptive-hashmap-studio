# mypy: ignore-errors

"""Mission Control desktop app scaffolding.

This module provides a minimal wrapper around a PyQt6 window so we can
incrementally build the Mission Control experience. When PyQt6 is unavailable
(e.g., in headless CI), attempting to launch the UI raises a friendly error.
"""

from __future__ import annotations

from typing import Optional, Sequence, Any, cast

from . import widgets
from .controller import MissionControlController
from .layout import create_dock

_QT_IMPORT_ERROR: Optional[Exception] = None

try:  # pragma: no cover - only executed when PyQt6 is installed
    from PyQt6.QtWidgets import QApplication, QMainWindow  # type: ignore[import-not-found]
    from PyQt6.QtCore import Qt  # type: ignore[import-not-found]
    from PyQt6.QtGui import QPalette, QColor  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - most environments won't have PyQt6
    _QT_IMPORT_ERROR = exc
    QApplication = cast(Any, object)
    QMainWindow = cast(Any, object)
    Qt = None  # type: ignore[assignment]
    QPalette = cast(Any, object)
    QColor = cast(Any, object)

if Qt is not None:  # pragma: no cover - only when PyQt6 is present
    class MissionControlWindow(QMainWindow):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self._controller: Optional["MissionControlController"] = None

        def set_controller(self, controller: "MissionControlController") -> None:
            self._controller = controller

        def closeEvent(self, event) -> None:  # type: ignore[override]
            if self._controller is not None:
                self._controller.shutdown()
            super().closeEvent(event)
else:  # pragma: no cover - PyQt6 missing
    MissionControlWindow = cast(Any, object)


def _require_qt() -> None:
    if _QT_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Mission Control requires PyQt6. Install with `pip install .[gui]` or `pip install PyQt6`."
        ) from _QT_IMPORT_ERROR


def _create_app(argv: Sequence[str] | None) -> QApplication:
    app = QApplication(list(argv) if argv is not None else [])  # type: ignore[call-arg]
    if Qt is not None:
        _apply_dark_theme(app)
    return app


def _apply_dark_theme(app: QApplication) -> None:
    try:
        app.setStyle("Fusion")
    except Exception:  # pragma: no cover - style might be missing
        pass

    palette = QPalette()
    base = QColor("#10151f")
    darker = QColor("#0a0f18")
    highlight = QColor("#3ba7ff")
    text = QColor("#e0e3f4")
    muted = QColor("#8a94a6")

    palette.setColor(QPalette.ColorRole.Window, base)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, darker)
    palette.setColor(QPalette.ColorRole.AlternateBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipBase, darker)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor("#1a2433"))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#0b0f17"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffb454"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)

    app.setPalette(palette)
    app.setStyleSheet(
        """
        QWidget {
            background-color: #10151f;
            color: #e0e3f4;
        }
        QLineEdit, QPlainTextEdit {
            background-color: #0b1019;
            border: 1px solid #1f2a3a;
            border-radius: 4px;
            padding: 4px 6px;
            selection-background-color: #3ba7ff;
            selection-color: #0b1019;
        }
        QPlainTextEdit {
            font-family: "JetBrains Mono", "Menlo", monospace;
            font-size: 12px;
        }
        QPushButton {
            background-color: #1a2433;
            border: 1px solid #27354b;
            padding: 6px 12px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #233044;
        }
        QPushButton:disabled {
            background-color: #141c29;
            color: #6e7684;
            border: 1px solid #202a3b;
        }
        QGroupBox {
            border: 1px solid #223042;
            border-radius: 6px;
            margin-top: 12px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 8px;
        }
        QDockWidget {
            titlebar-close-icon: url(none);
            titlebar-normal-icon: url(none);
        }
        QDockWidget::title {
            background-color: #0f1724;
            padding: 6px 8px;
            border-bottom: 1px solid #223042;
        }
        QScrollBar:vertical {
            background: #0b1019;
            width: 12px;
            margin: 0px 0px 0px 0px;
        }
        QScrollBar::handle:vertical {
            background: #243247;
            min-height: 20px;
            border-radius: 4px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        """
    )


def _create_window() -> QMainWindow:
    if Qt is not None:
        window = MissionControlWindow()  # type: ignore[call-arg]
    else:
        window = QMainWindow()  # type: ignore[call-arg]
    window.setWindowTitle("Adaptive Hash Map – Mission Control")
    window.resize(1280, 720)

    connection = widgets.ConnectionPane(window)  # type: ignore[call-arg]
    run_control = widgets.RunControlPane(window)  # type: ignore[call-arg]
    metrics = widgets.MetricsPane(window)  # type: ignore[call-arg]

    controller = MissionControlController(connection, metrics, run_control)

    if Qt is not None:
        window.set_controller(controller)  # type: ignore[attr-defined]
        window.setCentralWidget(metrics)  # type: ignore[call-arg]
        dock_connection = create_dock("Connection", connection, Qt.DockWidgetArea.LeftDockWidgetArea)  # type: ignore[attr-defined]
        dock_run_control = create_dock("Run Control", run_control, Qt.DockWidgetArea.LeftDockWidgetArea)  # type: ignore[attr-defined]
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_connection)  # type: ignore[attr-defined]
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_run_control)  # type: ignore[attr-defined]
        dock_run_control.setFeatures(dock_run_control.features() & ~dock_run_control.DockWidgetFeature.DockWidgetClosable)  # type: ignore[attr-defined]
        window.setStyleSheet(window.styleSheet() + "\nQMainWindow { background-color: #10151f; }")
    else:
        window.setCentralWidget(metrics)  # type: ignore[call-arg]
        setattr(window, "_controller", controller)

    return window


def run_mission_control(argv: Sequence[str] | None = None) -> int:
    """Launch the Mission Control UI.

    Returns the Qt exit code. Raises ``RuntimeError`` when PyQt6 is missing.
    """

    _require_qt()
    app = _create_app(argv)
    window = _create_window()
    window.show()
    return app.exec()  # type: ignore[call-arg]


__all__ = ["run_mission_control"]
