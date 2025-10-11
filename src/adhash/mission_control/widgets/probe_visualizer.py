# mypy: ignore-errors
"""Probe visualizer pane for Mission Control."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adhash.analysis import format_trace_lines

from .common import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)


class ProbeVisualizerPane(QWidget):  # type: ignore[misc]
    """Load and display probe traces exported by the CLI."""

    def __init__(self, parent: QWidget | None = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("probeVisualizerPane")
        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        heading = QLabel("Probe Visualizer")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        if Qt is not None:
            heading.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(heading)

        description = QLabel(
            "Load JSON traces produced by `hashmap-cli probe-visualize` to inspect collision paths."
        )  # type: ignore[call-arg]
        description.setWordWrap(True)
        layout.addWidget(description)

        controls = QHBoxLayout()  # type: ignore[call-arg]
        controls.setContentsMargins(0, 0, 0, 0)
        self._load_button = QPushButton("Load Trace JSON…")  # type: ignore[call-arg]
        self._load_button.clicked.connect(self._select_trace_file)  # type: ignore[attr-defined]
        controls.addWidget(self._load_button)
        controls.addStretch()
        layout.addLayout(controls)

        self._info_label = QLabel("No trace loaded")  # type: ignore[call-arg]
        self._info_label.setObjectName("traceInfoLabel")
        layout.addWidget(self._info_label)

        self._text = QPlainTextEdit(self)  # type: ignore[call-arg]
        self._text.setReadOnly(True)
        self._text.setObjectName("traceOutput")
        layout.addWidget(self._text, 1)

        self._current_path: Path | None = None
        self._trace: dict[str, Any] | None = None

    def display_trace(
        self,
        trace: dict[str, Any],
        *,
        source: Path | None = None,
        snapshot: str | None = None,
        seeds: list[str] | None = None,
        export_path: Path | None = None,
    ) -> None:
        """Render ``trace`` in the text box."""

        self._trace = trace
        self._current_path = source
        lines = format_trace_lines(trace, snapshot=snapshot, seeds=seeds, export_path=export_path)
        self._text.setPlainText("\n".join(lines))
        info_bits = []
        if source:
            info_bits.append(f"Source: {source}")
        else:
            info_bits.append("Source: in-memory")
        if snapshot:
            info_bits.append(f"Snapshot: {snapshot}")
        if seeds:
            info_bits.append(f"Seeds: {', '.join(seeds)}")
        self._info_label.setText(" | ".join(info_bits))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _select_trace_file(self) -> None:
        if QFileDialog is None:
            self._info_label.setText("File dialog requires PyQt6; install the GUI extras.")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select trace JSON", "", "JSON (*.json);;All files (*.*)"
        )
        if file_path:
            self.load_trace(Path(file_path))

    def load_trace(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._info_label.setText(f"Failed to load trace: {exc}")
            self._text.setPlainText("")
            return
        trace: dict[str, Any] | None
        if isinstance(data, dict) and "trace" in data and isinstance(data["trace"], dict):
            trace = data["trace"]
            seeds = data.get("seed_entries") if isinstance(data.get("seed_entries"), list) else None
            snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), str) else None
            export_path = (
                data.get("export_json") if isinstance(data.get("export_json"), str) else None
            )
        elif isinstance(data, dict):
            trace = data
            seeds = None
            snapshot = None
            export_path = None
        else:
            trace = None
        if trace is None:
            self._info_label.setText('Trace JSON must contain an object or {"trace": {...}}')
            self._text.setPlainText("")
            return
        export_path_path = Path(export_path) if isinstance(export_path, str) else None
        seeds_list = list(seeds) if isinstance(seeds, list) else None
        self.display_trace(
            trace, source=path, snapshot=snapshot, seeds=seeds_list, export_path=export_path_path
        )
