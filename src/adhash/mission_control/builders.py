"""Factory helpers for Mission Control widgets and windows."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from . import widgets
from .controller import MissionControlController

try:  # pragma: no cover - optional dependency in headless environments
    from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget  # type: ignore[import-not-found]
    from PyQt6.QtCore import Qt  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback when PyQt6 unavailable
    QApplication = None  # type: ignore[assignment]
    QMainWindow = None  # type: ignore[assignment]
    QWidget = None  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]


def build_widgets(parent: Optional[QWidget] = None) -> Tuple[widgets.ConnectionPane, widgets.RunControlPane, widgets.ConfigEditorPane, widgets.MetricsPane]:
    """Construct the core Mission Control widgets."""

    connection = widgets.ConnectionPane(parent)
    run_control = widgets.RunControlPane(parent)
    config_editor = widgets.ConfigEditorPane(parent)
    metrics = widgets.MetricsPane(parent)
    return connection, run_control, config_editor, metrics


def build_controller(connection: widgets.ConnectionPane, run_control: widgets.RunControlPane, config_editor: widgets.ConfigEditorPane, metrics: widgets.MetricsPane, *, poll_interval: float = 2.0) -> MissionControlController:
    """Wire up the Mission Control controller with the provided widgets."""

    return MissionControlController(connection, metrics, run_control, config_editor=config_editor, poll_interval=poll_interval)


def build_window(controller: MissionControlController, connection: widgets.ConnectionPane, run_control: widgets.RunControlPane, config_editor: widgets.ConfigEditorPane, metrics: widgets.MetricsPane) -> QMainWindow:
    """Create the Mission Control main window and embed widgets."""

    if QMainWindow is None:  # pragma: no cover - PyQt6 missing
        raise RuntimeError("PyQt6 not available")

    mission_window_cls = None
    if Qt is not None:
        try:  # lazy import to avoid circular reference
            from .app import MissionControlWindow  # type: ignore

            mission_window_cls = MissionControlWindow
        except Exception:  # pragma: no cover - fallback when custom subclass unavailable
            mission_window_cls = None

    window = mission_window_cls() if mission_window_cls is not None else QMainWindow()
    window.setObjectName("missionWindow")
    window.resize(1280, 720)
    if Qt is not None:
        tabs = widgets.QTabWidget(window)  # type: ignore[call-arg]
        tabs.setObjectName("missionTabs")
        tabs.addTab(metrics, "Telemetry")  # type: ignore[attr-defined]
        tabs.addTab(config_editor, "Config Editor")  # type: ignore[attr-defined]
        window.setCentralWidget(tabs)  # type: ignore[call-arg]
    else:
        window.setCentralWidget(metrics)  # type: ignore[call-arg]

    controller_ref = controller
    if Qt is not None:
        from .layout import create_dock
        if hasattr(window, "set_controller"):
            window.set_controller(controller_ref)  # type: ignore[attr-defined]
        dock_connection = create_dock("Connection Settings", connection, Qt.DockWidgetArea.LeftDockWidgetArea)  # type: ignore[attr-defined]
        dock_run = create_dock("Run Command", run_control, Qt.DockWidgetArea.LeftDockWidgetArea)  # type: ignore[attr-defined]
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_connection)  # type: ignore[attr-defined]
        window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock_run)  # type: ignore[attr-defined]
        dock_run.setFeatures(dock_run.features() & ~dock_run.DockWidgetFeature.DockWidgetClosable)  # type: ignore[attr-defined]
    else:
        setattr(window, "_controller", controller_ref)

    if not window.windowTitle():
        window.setWindowTitle("Adaptive Hash Map – Mission Control")
    return window


def build_app(argv: Sequence[str] | None = None) -> QApplication:
    if QApplication is None:  # pragma: no cover
        raise RuntimeError("PyQt6 not available")
    return QApplication(list(argv) if argv is not None else [])
