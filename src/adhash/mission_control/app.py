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
        _apply_futuristic_theme(app)
    return app


def _apply_futuristic_theme(app: QApplication) -> None:
    try:
        app.setStyle("Fusion")
    except Exception:  # pragma: no cover - style might be missing
        pass

    palette = QPalette()
    base = QColor("#121212")
    darker = QColor("#1A1A1A")
    panel = QColor("#18181F")
    highlight = QColor("#00FFAA")
    text = QColor("#EEEEEE")
    muted = QColor("#77808C")

    palette.setColor(QPalette.ColorRole.Window, base)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, darker)
    palette.setColor(QPalette.ColorRole.AlternateBase, panel)
    palette.setColor(QPalette.ColorRole.ToolTipBase, darker)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor("#1F1F1F"))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#061410"))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFD166"))
    palette.setColor(QPalette.ColorRole.Link, highlight)

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, muted)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, muted)

    app.setPalette(palette)
    app.setStyleSheet(
        """
        QWidget {
            background-color: #121212;
            color: #EEEEEE;
            font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;
            letter-spacing: 0.2px;
        }
        QMainWindow#missionWindow {
            background: qlineargradient(
                x1: 0, y1: 0, x2: 1, y2: 1,
                stop: 0 #121212,
                stop: 0.5 #0F1A29,
                stop: 1 #121212
            );
        }
        QLineEdit, QPlainTextEdit {
            background: #1E1E1E;
            border: 1px solid #2D2D2D;
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: #00FFAA;
            selection-color: #05120E;
        }
        QPlainTextEdit {
            font-family: "JetBrains Mono", "Fira Code", monospace;
            font-size: 12px;
            background: #161616;
        }
        QPushButton {
            background: #1F1F1F;
            border: 2px solid #2D2D2D;
            border-radius: 8px;
            padding: 8px 12px;
            color: #EEEEEE;
        }
        QPushButton:hover {
            border-color: #00FFAA;
            background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #1F1F1F, stop: 1 #2F2F2F);
        }
        QPushButton:disabled {
            background: #151515;
            color: #666A73;
            border: 2px solid #1B1B1B;
        }
        QGroupBox {
            border: 1px solid #2D2D2D;
            border-radius: 10px;
            margin-top: 18px;
            padding-top: 12px;
            font-weight: 600;
            background: rgba(18, 18, 32, 0.82);
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 12px;
            color: #00FFAA;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        QDockWidget {
            titlebar-close-icon: url(none);
            titlebar-normal-icon: url(none);
        }
        QDockWidget::title {
            background: #161623;
            padding: 6px 12px;
            border-bottom: 1px solid #25253A;
            color: #00FFAA;
            font-weight: 600;
            letter-spacing: 0.8px;
        }
        QScrollBar:vertical {
            background: #1E1E1E;
            width: 10px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #2D2D2D;
            min-height: 24px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::handle:vertical:hover {
            background: #00FFAA;
        }
        QLabel#connectionStatus {
            font-weight: 600;
        }
        QLabel#connectionStatus[statusKind="idle"] {
            color: #77808C;
        }
        QLabel#connectionStatus[statusKind="connected"] {
            color: #00FFAA;
        }
        QLabel#connectionStatus[statusKind="error"] {
            color: #FF6B6B;
        }
        QLabel#statusLabel {
            font-weight: 600;
        }
        QLabel#statusLabel[state="idle"] {
            color: #77808C;
        }
        QLabel#statusLabel[state="running"] {
            color: #00FFAA;
        }
        QLabel#statusLabel[state="stopping"] {
            color: #FFD166;
        }
        QLabel#statusLabel[state="completed"] {
            color: #4DD0E1;
        }
        QLabel#statusLabel[state="error"] {
            color: #FF6B6B;
        }
        QLabel#timerLabel {
            color: #7B61FF;
            font-weight: 500;
        }
        QPlainTextEdit#runLog, QPlainTextEdit#eventsLog {
            border: 1px solid #2D2D2D;
            border-radius: 8px;
            padding: 8px;
            background: #141414;
        }
        QToolTip {
            background-color: #1F1F1F;
            color: #EEEEEE;
            border: 1px solid #00FFAA;
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
        window.setObjectName("missionWindow")
        window.setCentralWidget(metrics)  # type: ignore[call-arg]
        dock_connection = create_dock("Connection", connection, Qt.DockWidgetArea.LeftDockWidgetArea)  # type: ignore[attr-defined]
        dock_run_control = create_dock("Run Control", run_control, Qt.DockWidgetArea.LeftDockWidgetArea)  # type: ignore[attr-defined]
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_connection)  # type: ignore[attr-defined]
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_run_control)  # type: ignore[attr-defined]
        dock_run_control.setFeatures(dock_run_control.features() & ~dock_run_control.DockWidgetFeature.DockWidgetClosable)  # type: ignore[attr-defined]
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
