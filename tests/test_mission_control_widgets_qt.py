from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, cast

import pytest

pytestmark = pytest.mark.qt

try:  # pragma: no cover - optional dependency in CI
    import pyqtgraph as pg  # noqa: F401 - ensure pyqtgraph is importable
    from PyQt6.QtWidgets import QApplication

    from adhash.mission_control import widgets
    from adhash.workloads import analyze_workload_csv
except Exception:  # pragma: no cover - skip when Qt missing  # noqa: BLE001
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

    def test_update_events_renders_latest_entries(_qt_app: QApplication) -> None:
        pane = widgets.MetricsPane()

        pane.update_events([
            {"type": "start", "backend": "chaining", "t": 0.0},
            {"type": "complete", "backend": "chaining", "t": 12.3456},
        ])

        rendered = pane.events_view.toPlainText().splitlines()

        assert rendered[0] == "12.35s — complete (backend=chaining)"
        assert rendered[1] == "0.00s — start (backend=chaining)"

    def test_builders_construct_controller_and_window(
        _qt_app: QApplication,
    ) -> None:
        from adhash.mission_control import build_controller, build_widgets, build_window

        (
            connection,
            run_control,
            config_editor,
            metrics,
            suite,
            dna,
            snapshot_pane,
            probe_pane,
        ) = build_widgets()
        controller = build_controller(
            connection,
            run_control,
            config_editor,
            metrics,
            suite,
            dna,
            snapshot_pane,
            probe_pane,
        )
        window = build_window(
            controller,
            connection,
            run_control,
            config_editor,
            metrics,
            suite,
            dna,
            snapshot_pane,
            probe_pane,
        )

        assert window.windowTitle()  # Mission window title assigned in app module
        assert hasattr(window, "centralWidget")
        central = window.centralWidget()
        assert central is not None
        central_any = cast(Any, central)
        if hasattr(central_any, "count"):
            assert central_any.count() >= 5

    def test_config_editor_save_and_presets(
        _qt_app: QApplication,
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
        assert cast(Any, pane.preset_combo).findData("demo") >= 0

    def test_run_control_builder_round_trip(_qt_app: QApplication, tmp_path: Path) -> None:
        pane = widgets.RunControlPane()

        exec_path = tmp_path / "hashmap_cli.py"
        config_path = tmp_path / "config.toml"
        csv_path = tmp_path / "data.csv"

        pane.exec_edit.setText(exec_path.as_posix())
        pane.config_builder_edit.setText(config_path.as_posix())
        pane.mode_edit.setText("adaptive")
        pane.csv_edit.setText(csv_path.as_posix())
        pane.metrics_port_edit.setText("1234")
        pane.extra_args_edit.setText("--flag value")

        pane._apply_builder_to_command()

        command = pane.command_edit.text()
        assert exec_path.as_posix() in command
        assert config_path.as_posix() in command
        assert csv_path.as_posix() in command
        assert "--metrics-port 1234" in command
        assert "--flag value" in command

        # Mutate the command directly and ensure the builder fields stay in sync.
        pane.command_edit.setText(
            "python alt_cli.py "
            f"--config {config_path} run-csv --csv {csv_path} "
            "--mode chaining --metrics-port 4321"
        )
        pane._populate_builder_from_command()

        assert pane.exec_edit.text() == "python alt_cli.py"
        assert pane.config_builder_edit.text() == config_path.as_posix()
        assert pane.mode_edit.text() == "chaining"
        assert pane.metrics_port_edit.text() == "4321"

    def test_benchmark_suite_cancel_discovery(
        qt_app: QApplication,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pane = widgets.BenchmarkSuitePane()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            pane,
            "_run_background",
            lambda work, success, _error: success(work()),
        )

        def slow_discover() -> list[Path]:
            time.sleep(0.05)
            return []

        monkeypatch.setattr(pane, "_discover_specs", slow_discover)

        pane.refresh_specs(select_first=False)
        assert pane.cancel_discovery_button.isEnabled()

        pane._cancel_discovery()
        assert not pane.cancel_discovery_button.isEnabled()
        assert pane.discover_button.isEnabled()

        # Allow the worker thread to finish and ensure state remains idle.
        timeout = time.monotonic() + 1.0
        while pane._discovering_specs and time.monotonic() < timeout:
            qt_app.processEvents()
            time.sleep(0.01)

        assert not pane._discovering_specs
        assert "cancelled" in pane.status_label.text().lower()

    def test_benchmark_suite_pane_lifecycle(
        qt_app: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pane = widgets.BenchmarkSuitePane()
        monkeypatch.setattr(
            pane,
            "_run_background",
            lambda work, success, _error: success(work()),
        )
        dna_pane = widgets.WorkloadDNAPane()
        pane.add_analysis_callback(
            lambda result, job, spec: dna_pane.set_primary_result(result, job.name, spec)
        )

        repo_root = Path(__file__).resolve().parent
        csv_path = None
        for candidate in [repo_root, *repo_root.parents]:
            maybe = candidate / "data" / "workloads" / "w_uniform.csv"
            if maybe.exists():
                csv_path = maybe
                break
        if csv_path is None:
            pytest.skip("w_uniform.csv not available for benchmark suite test")

        report_path = tmp_path / "report.md"
        spec_path = tmp_path / "suite.toml"
        spec_path.write_text(
            "\n".join([
                "[batch]",
                'hashmap_cli = "-m hashmap_cli"',
                f'report = "{report_path.name}"',
                "",
                "[[batch.jobs]]",
                'name = "demo"',
                'command = "run-csv"',
                f'csv = "{csv_path.as_posix()}"',
            ]),
            encoding="utf-8",
        )

        pane.spec_edit.setText(str(spec_path))
        pane._on_load_clicked()

        timeout = time.monotonic() + 2.0
        while pane._loading_spec and time.monotonic() < timeout:
            qt_app.processEvents()
            time.sleep(0.01)

        assert not pane._loading_spec
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

    def test_probe_visualizer_loads_trace(tmp_path: Path, _qt_app: QApplication) -> None:
        pane = widgets.ProbeVisualizerPane()

        trace_path = tmp_path / "trace.json"
        trace_path.write_text(
            json.dumps({
                "trace": {
                    "backend": "robinhood",
                    "operation": "get",
                    "key_repr": "'K1'",
                    "found": True,
                    "terminal": "match",
                    "path": [
                        {"step": 0, "slot": 3, "state": "occupied", "matches": True},
                    ],
                },
                "snapshot": "snapshot.pkl",
                "seed_entries": ["A=1"],
                "export_json": str(trace_path),
            }),
            encoding="utf-8",
        )

        pane.load_trace(trace_path)

        assert "Probe visualization" in pane._text.toPlainText()
        assert "Seed entries" in pane._text.toPlainText()
        assert trace_path.as_posix() in pane._info_label.text()

    def test_probe_visualizer_handles_bad_json(tmp_path: Path, _qt_app: QApplication) -> None:
        pane = widgets.ProbeVisualizerPane()

        bad_path = tmp_path / "bad.json"
        bad_path.write_text("not-json", encoding="utf-8")

        pane.load_trace(bad_path)

        assert "Failed to load trace" in pane._info_label.text()
        assert pane._text.toPlainText() == ""
