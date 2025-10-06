# mypy: ignore-errors

"""Mission Control desktop app scaffolding.

This module provides a minimal wrapper around a PyQt6 window so we can
incrementally build the Mission Control experience. When PyQt6 is unavailable
(e.g., in headless CI), attempting to launch the UI raises a friendly error.
"""

from __future__ import annotations

from importlib import resources
from typing import Optional, Sequence, Any, cast, TYPE_CHECKING

from .builders import build_app as _build_app, build_controller, build_widgets, build_window

if TYPE_CHECKING:
    from .controller import MissionControlController

_QT_IMPORT_ERROR: Optional[Exception] = None

try:  # pragma: no cover - only executed when PyQt6 is installed
    from PyQt6.QtWidgets import QApplication, QMainWindow  # type: ignore[import-not-found]
    from PyQt6.QtCore import Qt, QTimer  # type: ignore[import-not-found]
    from PyQt6.QtGui import QPalette, QColor, QLinearGradient, QBrush  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - most environments won't have PyQt6
    _QT_IMPORT_ERROR = exc
    QApplication = cast(Any, object)
    QMainWindow = cast(Any, object)
    Qt = None  # type: ignore[assignment]
    QPalette = cast(Any, object)
    QColor = cast(Any, object)
    QTimer = cast(Any, None)
    QLinearGradient = cast(Any, object)
    QBrush = cast(Any, object)

if Qt is not None:  # pragma: no cover - only when PyQt6 is present
    class MissionControlWindow(QMainWindow):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self._controller: Optional["MissionControlController"] = None
            self._gradient_angle = 0
            self._gradient_timer: Optional[QTimer] = None
            self.setAutoFillBackground(True)
            self._install_gradient()

        def set_controller(self, controller: "MissionControlController") -> None:
            self._controller = controller

        def closeEvent(self, event) -> None:  # type: ignore[override]
            if self._controller is not None:
                self._controller.shutdown()
            if self._gradient_timer is not None:
                self._gradient_timer.stop()
                self._gradient_timer.deleteLater()
            super().closeEvent(event)

        def resizeEvent(self, event) -> None:  # type: ignore[override]
            super().resizeEvent(event)
            self._update_gradient()

        def _install_gradient(self) -> None:
            if QTimer is None:
                return
            self._gradient_timer = QTimer(self)
            self._gradient_timer.setInterval(60)
            self._gradient_timer.timeout.connect(self._advance_gradient)  # type: ignore[attr-defined]
            self._gradient_timer.start()
            self._update_gradient()

        def _advance_gradient(self) -> None:
            self._gradient_angle = (self._gradient_angle + 2) % 360
            self._update_gradient()

        def _update_gradient(self) -> None:
            if Qt is None:
                return
            width = max(self.width(), 1)
            height = max(self.height(), 1)
            grad = QLinearGradient(0, 0, width, height)
            grad.setColorAt(0, QColor.fromHsv(self._gradient_angle, 180, 60))
            grad.setColorAt(0.5, QColor.fromHsv((self._gradient_angle + 45) % 360, 160, 80))
            grad.setColorAt(1, QColor.fromHsv((self._gradient_angle + 120) % 360, 180, 40))
            palette = self.palette()
            palette.setBrush(QPalette.ColorRole.Window, QBrush(grad))
            self.setPalette(palette)
else:  # pragma: no cover - PyQt6 missing
    MissionControlWindow = cast(Any, object)


def _load_stylesheet() -> str:
    try:
        return resources.files("adhash.mission_control.widgets").joinpath("styles.qss").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):  # pragma: no cover - fallback in packaging scenarios
        return ""


def _require_qt() -> None:
    if _QT_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Mission Control requires PyQt6. Install with `pip install .[gui]` or `pip install PyQt6`."
        ) from _QT_IMPORT_ERROR


def _create_app(argv: Sequence[str] | None) -> QApplication:
    app = _build_app(argv)
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
    stylesheet = _load_stylesheet()
    if not stylesheet:
        stylesheet = """
        QWidget {
            background-color: #121212;
            color: #EEEEEE;
            font-family: '-apple-system', 'Helvetica Neue', 'Arial', 'Inter', sans-serif;
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
        QWidget#missionPane {
            border: 1px solid #1F2A33;
            border-radius: 16px;
            background: qradialgradient(
                cx:0.3, cy:0.2, radius:1.2,
                stop:0 rgba(32, 47, 65, 0.32),
                stop:1 rgba(12, 16, 24, 0.85)
            );
            margin-top: 0;
        }
        QWidget#missionPane[paneKind="run"] {
            border-color: #27384A;
        }
        QWidget#missionPane[paneKind="metrics"] {
            border-color: #352D5C;
        }
        QWidget#missionPane[paneKind="config"] {
            border-color: #1F2A40;
        }
        QWidget#missionPane[paneKind="suite"] {
            border-color: #26413C;
        }
        QWidget#missionPane[paneKind="dna"] {
            border-color: #2E3D4F;
        }
        QDockWidget {
            titlebar-close-icon: url(none);
            titlebar-normal-icon: url(none);
        }
        QWidget#dockTitleBar {
            background: transparent;
            border-bottom: 1px solid rgba(31, 42, 51, 0.6);
        }
        QLabel#dockGrip {
            color: #2D3D4F;
            font-size: 16px;
        }
        QLabel#dockGrip:hover {
            color: #00FFAA;
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
        QLabel#configBindingLabel {
            color: #94a3b8;
            font-size: 12px;
        }
        QLabel#configBindingLabel[statusKind="connected"] {
            color: #00FFAA;
        }
        QLabel#paneHeading {
            color: #00FFAA;
            font-size: 13px;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        QLabel#histStatusLabel {
            color: #64748b;
            font-style: italic;
            padding: 4px 0;
        }
        QWidget#missionPane QPushButton {
            border-radius: 6px;
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
        QLabel#dnaSummaryLabel {
            color: #cbd5f5;
        }
        QLabel#dnaBaselineLabel {
            color: #94a3b8;
        }
        QLabel#dnaBaselineLabel[baselineSet="true"] {
            color: #00FFAA;
        }
        QComboBox#dnaViewSelector, QSpinBox#dnaBucketLimit {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 4px 6px;
            color: #f8fafc;
        }
        QPlainTextEdit#dnaDetailsView {
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 10px;
            color: #e2e8f0;
            font-family: "JetBrains Mono", "Fira Code", monospace;
            font-size: 12px;
        }
        QLabel#suiteStatusLabel {
            font-weight: 600;
        }
        QLabel#suiteStatusLabel[state="idle"] {
            color: #77808C;
        }
        QLabel#suiteStatusLabel[state="running"] {
            color: #00FFAA;
        }
        QLabel#suiteStatusLabel[state="stopping"] {
            color: #FFD166;
        }
        QLabel#suiteStatusLabel[state="completed"] {
            color: #4DD0E1;
        }
        QLabel#suiteStatusLabel[state="error"] {
            color: #FF6B6B;
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
        QWidget#opsPlot, QWidget#loadPlot, QWidget#latencyPlot, QWidget#probePlot, QWidget#heatmapPlot {
            border: 1px solid #2D2D2D;
            border-radius: 12px;
            background-color: #11141d;
        }
        QTabWidget#metricsTabs::pane {
            border: 1px solid #1F2A33;
            border-radius: 12px;
            margin-top: 6px;
            background: #0F172A;
        }
        QTabWidget#metricsTabs::tab-bar {
            left: 12px;
        }
        QTabBar::tab {
            background: #11141d;
            color: #94a3b8;
            padding: 6px 12px;
            border: 1px solid #1F2937;
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            margin-right: 6px;
        }
        QTabBar::tab:selected {
            color: #00FFAA;
            border-color: #00FFAA;
        }
        QTabBar::tab:hover {
            color: #38BDF8;
        }
        QToolTip {
            background-color: #1F1F1F;
            color: #EEEEEE;
            border: 1px solid #00FFAA;
        }
        """
    app.setStyleSheet(stylesheet)


def _create_window() -> QMainWindow:
    (
        connection,
        run_control,
        config_editor,
        metrics,
        suite_manager,
        dna_pane,
        snapshot_pane,
        probe_pane,
    ) = build_widgets()
    controller = build_controller(
        connection,
        run_control,
        config_editor,
        metrics,
        suite_manager,
        dna_pane,
        snapshot_pane,
        probe_pane,
    )
    window = build_window(
        controller,
        connection,
        run_control,
        config_editor,
        metrics,
        suite_manager,
        dna_pane,
        snapshot_pane,
        probe_pane,
    )
    window.setWindowTitle("Adaptive Hash Map – Mission Control")
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
