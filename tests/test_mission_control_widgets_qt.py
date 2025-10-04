from __future__ import annotations

import os
from pathlib import Path
import pytest

try:  # pragma: no cover - optional dependency in CI
    from PyQt6.QtWidgets import QApplication
    import pyqtgraph as pg  # noqa: F401  - ensure pyqtgraph is importable
    from adhash.mission_control import widgets
except Exception:  # pragma: no cover - skip when Qt missing
    pytestmark = pytest.mark.skip(reason="PyQt6/pyqtgraph not available")
else:

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


    @pytest.fixture(scope="module")
    def qt_app() -> QApplication:  # pragma: no cover - glue for Qt tests
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app


    def test_update_events_renders_latest_entries(qt_app: QApplication) -> None:
        pane = widgets.MetricsPane()

        pane.update_events(
            [
                {"type": "start", "backend": "chaining", "t": 0.0},
                {"type": "complete", "backend": "chaining", "t": 12.3456},
            ]
        )

        rendered = pane.events_view.toPlainText().splitlines()

        assert rendered[0] == "12.35s — complete (backend=chaining)"
        assert rendered[1] == "0.00s — start (backend=chaining)"


    def test_builders_construct_controller_and_window(
        qt_app: QApplication,
    ) -> None:
        from adhash.mission_control import build_controller, build_widgets, build_window

        connection, run_control, config_editor, metrics = build_widgets()
        controller = build_controller(connection, run_control, config_editor, metrics)
        window = build_window(controller, connection, run_control, config_editor, metrics)

        assert window.windowTitle()  # Mission window title assigned in app module
        assert hasattr(window, "centralWidget")


    def test_config_editor_save_and_presets(
        qt_app: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        preset_dir = tmp_path / "presets"
        monkeypatch.setenv("ADHASH_PRESETS_DIR", str(preset_dir))

        pane = widgets.ConfigEditorPane()
        run_control = widgets.RunControlPane()
        pane.add_config_saved_callback(run_control.apply_config_path)

        cfg_path = tmp_path / "config.toml"
        pane.path_edit.setText(str(cfg_path))
        pane._on_save_clicked()

        assert cfg_path.exists()
        assert pane.binding_label.text().endswith(str(cfg_path))

        resolved = str(cfg_path.expanduser().resolve())
        assert resolved in run_control.command_edit.text()
        assert run_control.config_label.text().endswith(resolved)

        pane.new_preset_edit.setText("demo")
        pane._on_save_preset()

        preset_path = preset_dir / "demo.toml"
        assert preset_path.exists()
        assert pane.preset_combo.findData("demo") >= 0  # type: ignore[attr-defined]
