"""Factory helpers for Mission Control widgets and windows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from . import widgets
from .controller import MissionControlController

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PyQt6.QtCore import Qt as QtNamespace
    from PyQt6.QtWidgets import (
        QApplication as QApplicationLike,
    )
    from PyQt6.QtWidgets import (
        QMainWindow as QMainWindowLike,
    )
    from PyQt6.QtWidgets import (
        QWidget as QWidgetLike,
    )
else:  # pragma: no cover - fallback aliases
    QtNamespace = Any  # type: ignore[assignment]
    QApplicationLike = Any  # type: ignore[assignment]
    QMainWindowLike = Any  # type: ignore[assignment]
    QWidgetLike = Any  # type: ignore[assignment]

try:  # pragma: no cover - optional dependency in headless environments
    from PyQt6 import QtCore as _QtCore  # type: ignore[import-not-found]
    from PyQt6 import QtWidgets as _QtWidgets
except ImportError:  # pragma: no cover - fallback when PyQt6 unavailable
    _QtCore = None  # type: ignore[assignment]
    _QtWidgets = None  # type: ignore[assignment]

_QApplication = getattr(_QtWidgets, "QApplication", None)
_QMainWindow = getattr(_QtWidgets, "QMainWindow", None)
_QWidget = getattr(_QtWidgets, "QWidget", None)
_Qt = getattr(_QtCore, "Qt", None)

QAPPLICATION_CLS: type[QApplicationLike] | None = cast(type[QApplicationLike] | None, _QApplication)
QMAINWINDOW_CLS: type[QMainWindowLike] | None = cast(type[QMainWindowLike] | None, _QMainWindow)
QWIDGET_CLS: type[QWidgetLike] | None = cast(type[QWidgetLike] | None, _QWidget)
QT_NAMESPACE: QtNamespace | None = cast(QtNamespace | None, _Qt)


def build_widgets(
    parent: QWidgetLike | None = None,
) -> tuple[
    widgets.ConnectionPane,
    widgets.RunControlPane,
    widgets.ConfigEditorPane,
    widgets.MetricsPane,
    widgets.BenchmarkSuitePane,
    widgets.WorkloadDNAPane,
    widgets.SnapshotInspectorPane,
    widgets.ProbeVisualizerPane,
]:
    """Construct the core Mission Control widgets."""

    connection = widgets.ConnectionPane(parent)
    run_control = widgets.RunControlPane(parent)
    config_editor = widgets.ConfigEditorPane(parent)
    metrics = widgets.MetricsPane(parent)
    suite_manager = widgets.BenchmarkSuitePane(parent)
    dna_pane = widgets.WorkloadDNAPane(parent)
    snapshot_inspector = widgets.SnapshotInspectorPane(parent)
    probe_visualizer = widgets.ProbeVisualizerPane(parent)
    return (
        connection,
        run_control,
        config_editor,
        metrics,
        suite_manager,
        dna_pane,
        snapshot_inspector,
        probe_visualizer,
    )


def build_controller(
    connection: widgets.ConnectionPane,
    run_control: widgets.RunControlPane,
    config_editor: widgets.ConfigEditorPane,
    metrics: widgets.MetricsPane,
    suite_manager: widgets.BenchmarkSuitePane,
    dna_pane: widgets.WorkloadDNAPane,
    snapshot_inspector: widgets.SnapshotInspectorPane,
    probe_visualizer: widgets.ProbeVisualizerPane,
    *,
    poll_interval: float = 2.0,
) -> MissionControlController:
    """Wire up the Mission Control controller with the provided widgets."""

    return MissionControlController(
        connection,
        metrics,
        run_control,
        config_editor=config_editor,
        suite_manager=suite_manager,
        dna_panel=dna_pane,
        snapshot_panel=snapshot_inspector,
        probe_panel=probe_visualizer,
        poll_interval=poll_interval,
    )


def build_window(
    controller: MissionControlController,
    connection: widgets.ConnectionPane,
    run_control: widgets.RunControlPane,
    config_editor: widgets.ConfigEditorPane,
    metrics: widgets.MetricsPane,
    suite_manager: widgets.BenchmarkSuitePane,
    dna_pane: widgets.WorkloadDNAPane,
    snapshot_inspector: widgets.SnapshotInspectorPane,
    probe_visualizer: widgets.ProbeVisualizerPane,
) -> QMainWindowLike:
    """Create the Mission Control main window and embed widgets."""

    if QMAINWINDOW_CLS is None:  # pragma: no cover - PyQt6 missing
        raise RuntimeError("PyQt6 not available")

    mission_window_cls: type[QMainWindowLike] | None = None
    if QT_NAMESPACE is not None:
        try:  # pragma: no cover - lazy import to avoid circular reference
            from .app import MissionControlWindow
        except ImportError:
            mission_window_cls = None
        else:
            mission_window_cls = cast(type[QMainWindowLike], MissionControlWindow)

    window_cls = mission_window_cls or QMAINWINDOW_CLS
    if window_cls is None:
        raise RuntimeError("Unable to resolve Mission Control window class")
    window = window_cls()  # type: ignore[call-arg]
    window.setObjectName("missionWindow")
    window.resize(1280, 720)
    if QT_NAMESPACE is not None and QWIDGET_CLS is not None:
        tabs = widgets.QTabWidget(window)  # type: ignore[call-arg]
        tabs.setObjectName("missionTabs")
        tabs.addTab(metrics, "Telemetry")  # type: ignore[attr-defined]
        tabs.addTab(config_editor, "Config Editor")  # type: ignore[attr-defined]
        tabs.addTab(snapshot_inspector, "Snapshot Inspector")  # type: ignore[attr-defined]
        tabs.addTab(suite_manager, "Benchmark Suites")  # type: ignore[attr-defined]
        tabs.addTab(dna_pane, "Workload DNA")  # type: ignore[attr-defined]
        tabs.addTab(probe_visualizer, "Probe Visualizer")  # type: ignore[attr-defined]
        window.setCentralWidget(tabs)  # type: ignore[call-arg]
    else:
        window.setCentralWidget(metrics)  # type: ignore[call-arg]

    controller_ref = controller
    if QT_NAMESPACE is not None:
        from .layout import create_dock

        if hasattr(window, "set_controller"):
            window.set_controller(controller_ref)  # type: ignore[attr-defined]
        dock_area = QT_NAMESPACE.DockWidgetArea.LeftDockWidgetArea  # type: ignore[attr-defined]
        dock_connection = create_dock("Connection Settings", connection, dock_area)  # type: ignore[attr-defined]
        dock_run = create_dock("Run Command", run_control, dock_area)  # type: ignore[attr-defined]
        window.addDockWidget(dock_area, dock_connection)  # type: ignore[attr-defined]
        window.addDockWidget(dock_area, dock_run)  # type: ignore[attr-defined]
        dock_run.setFeatures(dock_run.features() & ~dock_run.DockWidgetFeature.DockWidgetClosable)  # type: ignore[attr-defined]
    else:
        window._controller = controller_ref

    if not window.windowTitle():
        window.setWindowTitle("Adaptive Hash Map – Mission Control")
    return window


def build_app(argv: Sequence[str] | None = None) -> QApplicationLike:
    if QAPPLICATION_CLS is None:  # pragma: no cover
        raise RuntimeError("PyQt6 not available")
    return QAPPLICATION_CLS(list(argv) if argv is not None else [])
