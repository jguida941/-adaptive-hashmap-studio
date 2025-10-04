from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

try:  # pragma: no cover - optional dependency in CI
    from PyQt6.QtWidgets import QApplication
    import pyqtgraph as pg  # type: ignore[import]  # noqa: F401 - ensure pyqtgraph is importable
    from adhash.mission_control import widgets
    from adhash.workloads import analyze_workload_csv
except Exception:  # pragma: no cover - skip when Qt missing
    pytestmark = pytest.mark.skip(reason="PyQt6/pyqtgraph not available")
else:

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from adhash.batch.runner import load_spec


    @pytest.fixture(scope="module")
    def qt_app() -> QApplication:  # pragma: no cover - glue for Qt tests
        app = QApplication.instance()
        if app is not None:
            return cast(QApplication, app)
        return QApplication([])


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

        connection, run_control, config_editor, metrics, suite, dna = build_widgets()
        controller = build_controller(connection, run_control, config_editor, metrics, suite, dna)
        window = build_window(controller, connection, run_control, config_editor, metrics, suite, dna)

        assert window.windowTitle()  # Mission window title assigned in app module
        assert hasattr(window, "centralWidget")
        central = window.centralWidget()
        assert central is not None
        if hasattr(central, "count"):
            assert central.count() >= 4  # type: ignore[attr-defined]


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
    def test_benchmark_suite_pane_lifecycle(
        qt_app: QApplication,
        tmp_path: Path,
    ) -> None:
        pane = widgets.BenchmarkSuitePane()
        dna_pane = widgets.WorkloadDNAPane()
        pane.add_analysis_callback(lambda result, job, spec: dna_pane.set_primary_result(result, job.name, spec))

        repo_root = Path(__file__).resolve().parents[1]
        csv_path = repo_root / "data" / "workloads" / "w_uniform.csv"
        hashmap_cli = repo_root / "hashmap_cli.py"
        report_path = tmp_path / "report.md"
        spec_path = tmp_path / "suite.toml"
        spec_path.write_text(
            "\n".join(
                [
                    "[batch]",
                    f"hashmap_cli = \"{hashmap_cli.as_posix()}\"",
                    f"report = \"{report_path.name}\"",
                    "",
                    "[[batch.jobs]]",
                    "name = \"demo\"",
                    "command = \"run-csv\"",
                    f"csv = \"{csv_path.as_posix()}\"",
                ]
            ),
            encoding="utf-8",
        )

        pane.spec_edit.setText(str(spec_path))
        pane._on_load_clicked()

        assert "1 jobs" in pane.summary_label.text()
        assert "demo" in pane.summary_view.toPlainText()

        spec = load_spec(spec_path)
        pane.prepare_for_run(spec_path, spec)
        pane.append_log("suite started")
        pane._on_analyze_clicked()
        pane.finalize_run(0)

        history = pane.history_view.toPlainText()
        assert "report:" in history
        assert "Workload DNA" in pane.analysis_view.toPlainText()
        assert "Workload DNA" in dna_pane.details_view.toPlainText()
        baseline_result = analyze_workload_csv(csv_path)
        dna_pane.pin_baseline(baseline_result, "baseline")
        assert "Baseline" in dna_pane.baseline_label.text()
