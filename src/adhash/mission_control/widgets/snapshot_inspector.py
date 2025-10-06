"""Snapshot inspection pane for Mission Control."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from adhash.io.snapshot import load_snapshot_any
from adhash.io.snapshot_header import SnapshotDescriptor, describe_snapshot

from .common import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    Qt,
    QSlider,
    QDoubleSpinBox,
)


def _iter_items(obj: Any) -> Iterable[Tuple[Any, Any]]:
    """Yield key/value pairs from supported snapshot payloads."""

    if obj is None:
        return []
    if hasattr(obj, "items") and callable(getattr(obj, "items")):
        try:
            iterable = getattr(obj, "items")()  # type: ignore[call-arg]
            if isinstance(iterable, Iterable):
                return iterable
        except Exception:
            pass
    if isinstance(obj, dict):
        return obj.items()
    return []


def _pretty(value: Any, limit: int = 120) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


class SnapshotInspectorPane(QWidget):  # type: ignore[misc]
    """UI widget that surfaces snapshot metadata and key search utilities."""

    _MAX_PREVIEW = 200

    def __init__(self, parent: Optional[QWidget] = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "snapshot")

        self._descriptor: Optional[SnapshotDescriptor] = None
        self._payload: Any = None
        self._preview: List[Tuple[Any, Any]] = []

        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Snapshot Inspector")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        path_row = QHBoxLayout()  # type: ignore[call-arg]
        self.path_edit = QLineEdit("snapshots/demo.pkl.gz")  # type: ignore[call-arg]
        self.path_edit.setObjectName("snapshotPathEdit")
        self.browse_button = QPushButton("Browse…")  # type: ignore[call-arg]
        self.load_button = QPushButton("Load")  # type: ignore[call-arg]
        path_row.addWidget(QLabel("Path:"))  # type: ignore[call-arg]
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.browse_button)
        path_row.addWidget(self.load_button)
        layout.addLayout(path_row)

        self.status_label = QLabel("")  # type: ignore[call-arg]
        if Qt is not None:
            self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.status_label.setObjectName("snapshotStatusLabel")
        layout.addWidget(self.status_label)

        header_heading = QLabel("Header metadata")  # type: ignore[call-arg]
        header_heading.setObjectName("paneSubHeading")
        layout.addWidget(header_heading)

        self.header_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.header_view.setReadOnly(True)
        self.header_view.setObjectName("snapshotHeaderView")
        self.header_view.setMaximumBlockCount(200)
        layout.addWidget(self.header_view)

        summary_heading = QLabel("Snapshot summary")  # type: ignore[call-arg]
        summary_heading.setObjectName("paneSubHeading")
        layout.addWidget(summary_heading)

        self.summary_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.summary_view.setReadOnly(True)
        self.summary_view.setObjectName("snapshotSummaryView")
        layout.addWidget(self.summary_view)

        filter_row = QHBoxLayout()  # type: ignore[call-arg]
        self.filter_edit = QLineEdit()  # type: ignore[call-arg]
        self.filter_edit.setPlaceholderText("Filter keys (substring)")  # type: ignore[attr-defined]
        self.preview_limit = QSlider(Qt.Orientation.Horizontal) if Qt is not None else None  # type: ignore[call-arg]
        self.limit_label = QLabel("Preview: 50")  # type: ignore[call-arg]
        if self.preview_limit is not None:
            self.preview_limit.setMinimum(10)
            self.preview_limit.setMaximum(self._MAX_PREVIEW)
            self.preview_limit.setValue(50)
            self.preview_limit.setTickInterval(10)
        filter_row.addWidget(QLabel("Filter:"))  # type: ignore[call-arg]
        filter_row.addWidget(self.filter_edit, 1)
        if self.preview_limit is not None:
            filter_row.addWidget(self.preview_limit)
        filter_row.addWidget(self.limit_label)
        layout.addLayout(filter_row)

        preview_heading = QLabel("Preview (first matches)")  # type: ignore[call-arg]
        preview_heading.setObjectName("paneSubHeading")
        layout.addWidget(preview_heading)

        self.preview_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.preview_view.setReadOnly(True)
        self.preview_view.setObjectName("snapshotPreviewView")
        layout.addWidget(self.preview_view)

        search_row = QHBoxLayout()  # type: ignore[call-arg]
        self.search_edit = QLineEdit()  # type: ignore[call-arg]
        self.search_edit.setPlaceholderText("Exact key search (literal or string)")  # type: ignore[attr-defined]
        self.search_button = QPushButton("Find")  # type: ignore[call-arg]
        self.alert_spin = QDoubleSpinBox() if QDoubleSpinBox is not None else None  # type: ignore[call-arg]
        if self.alert_spin is not None:
            self.alert_spin.setRange(0.0, 100.0)
            self.alert_spin.setDecimals(2)
            self.alert_spin.setSuffix(" % load warn")
            self.alert_spin.setValue(85.0)
        search_row.addWidget(QLabel("Key:"))  # type: ignore[call-arg]
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.search_button)
        if self.alert_spin is not None:
            search_row.addWidget(self.alert_spin)
        layout.addLayout(search_row)

        result_heading = QLabel("Search result")  # type: ignore[call-arg]
        result_heading.setObjectName("paneSubHeading")
        layout.addWidget(result_heading)

        self.result_view = QPlainTextEdit()  # type: ignore[call-arg]
        self.result_view.setReadOnly(True)
        self.result_view.setObjectName("snapshotResultView")
        layout.addWidget(self.result_view)

        layout.addStretch()

        self.browse_button.clicked.connect(self._browse)  # type: ignore[attr-defined]
        self.load_button.clicked.connect(self._load_snapshot)  # type: ignore[attr-defined]
        self.filter_edit.textChanged.connect(self._refresh_preview)  # type: ignore[attr-defined]
        self.search_button.clicked.connect(self._search_key)  # type: ignore[attr-defined]
        if self.preview_limit is not None:
            self.preview_limit.valueChanged.connect(self._refresh_limit_label)  # type: ignore[attr-defined]
            self.preview_limit.valueChanged.connect(lambda _val: self._refresh_preview())  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    def _browse(self) -> None:
        if QFileDialog is None:
            self._set_status("File dialog unavailable (PyQt missing)", error=True)
            return
        selected, _ = QFileDialog.getOpenFileName(self, "Select snapshot", "", "Snapshots (*.pkl *.pkl.gz)")  # type: ignore[call-arg]
        if selected:
            self.path_edit.setText(selected)

    def _set_status(self, message: str, *, error: bool = False) -> None:
        style = "color:#f97316;" if error else "color:#94a3b8;"
        self.status_label.setStyleSheet(style)
        self.status_label.setText(message)

    def _load_snapshot(self) -> None:
        path = Path(self.path_edit.text().strip()).expanduser()
        if not path.exists():
            self._set_status(f"Snapshot not found: {path}", error=True)
            return
        descriptor: Optional[SnapshotDescriptor]
        try:
            descriptor = describe_snapshot(path)
        except Exception:
            descriptor = None
        try:
            payload = load_snapshot_any(str(path))
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Failed to load snapshot: {exc}", error=True)
            self._descriptor = None
            self._payload = None
            self._preview = []
            self.header_view.setPlainText("")
            self.summary_view.setPlainText("")
            self.preview_view.setPlainText("")
            self.result_view.setPlainText("")
            return

        self._descriptor = descriptor
        self._payload = payload
        status = "Loaded snapshot"
        if descriptor is None:
            status = "Loaded legacy snapshot"
        self._set_status(f"{status} {path.name}")
        self._render_header(descriptor, path)
        self._render_summary(payload)
        self._refresh_preview()
        self.result_view.setPlainText("")

    def _render_header(self, descriptor: Optional[SnapshotDescriptor], path: Path) -> None:
        lines = [
            f"File: {path}",
            f"Size: {path.stat().st_size:,} bytes",
        ]
        if descriptor is None:
            lines.append("Format: legacy pickle (no versioned header)")
        else:
            header = descriptor.header
            lines.extend(
                [
                    f"Version: {header.version}",
                    f"Compressed: {'yes' if descriptor.compressed else 'no'}",
                    f"Payload bytes: {header.payload_len:,}",
                    f"Checksum length: {header.checksum_len}",
                    f"Checksum (hex): {descriptor.checksum_hex}",
                ]
            )
        self.header_view.setPlainText("\n".join(lines))

    def _render_summary(self, payload: Any) -> None:
        if payload is None:
            self.summary_view.setPlainText("Payload empty or unsupported.")
            return
        lines = [f"Object type: {type(payload).__name__}"]
        if hasattr(payload, "backend_name"):
            try:
                lines.append(f"Backend: {payload.backend_name()}")
            except Exception:
                pass
        if hasattr(payload, "cfg"):
            try:
                cfg = getattr(payload, "cfg")
                lines.append(f"Adaptive start backend: {cfg.start_backend}")
                lines.append(f"Incremental batch: {cfg.incremental_batch}")
            except Exception:
                pass
        if hasattr(payload, "load_factor"):
            try:
                lf = payload.load_factor()
                lines.append(f"Load factor: {lf:.4f}")
            except Exception:
                pass
        if hasattr(payload, "tombstone_ratio"):
            try:
                tr = payload.tombstone_ratio()
                lines.append(f"Tombstone ratio: {tr:.4f}")
            except Exception:
                pass
        if hasattr(payload, "max_group_len"):
            try:
                mg = payload.max_group_len()
                lines.append(f"Max group length: {mg}")
            except Exception:
                pass
        if hasattr(payload, "items") or isinstance(payload, dict):
            try:
                size = len(payload)  # type: ignore[arg-type]
                lines.append(f"Item count: {size:,}")
            except Exception:
                pass
        self.summary_view.setPlainText("\n".join(lines))

    def _refresh_limit_label(self) -> None:
        if self.preview_limit is not None:
            self.limit_label.setText(f"Preview: {self.preview_limit.value()}")

    def _refresh_preview(self) -> None:
        if self._payload is None:
            self.preview_view.setPlainText("")
            return
        filter_text = self.filter_edit.text().strip()
        limit = self.preview_limit.value() if self.preview_limit is not None else 50
        entries = []
        try:
            for key, value in _iter_items(self._payload):
                key_text = str(key)
                if filter_text and filter_text.lower() not in key_text.lower():
                    continue
                entries.append((key, value))
                if len(entries) >= min(limit, self._MAX_PREVIEW):
                    break
        except Exception as exc:  # noqa: BLE001
            self.preview_view.setPlainText(f"Failed to iterate entries: {exc}")
            return
        self._preview = entries
        if not entries:
            self.preview_view.setPlainText("No entries match the current filter.")
            return
        lines = [f"{_pretty(k)} -> {_pretty(v)}" for k, v in entries]
        self.preview_view.setPlainText("\n".join(lines))

    def _search_key(self) -> None:
        if self._payload is None:
            self.result_view.setPlainText("Load a snapshot first.")
            return
        raw = self.search_edit.text().strip()
        if not raw:
            self.result_view.setPlainText("Enter a key to search.")
            return
        key: Any
        try:
            key = ast.literal_eval(raw)
        except Exception:
            key = raw

        lookup = getattr(self._payload, "get", None)
        value: Any = None
        found = False
        if callable(lookup):
            try:
                value = lookup(key)
                found = value is not None
            except Exception:
                found = False
        if not found:
            for candidate, candidate_value in _iter_items(self._payload):
                if candidate == key:
                    value = candidate_value
                    found = True
                    break

        if found:
            text = [f"Key: {repr(key)}", f"Value: {_pretty(value, limit=200)}"]
        else:
            text = [f"Key {repr(key)} not found in snapshot"]
        if self.alert_spin is not None and self._descriptor is not None:
            try:
                load_factor = getattr(self._payload, "load_factor")()
                warn = self.alert_spin.value() / 100.0
                if load_factor is not None and load_factor >= warn:
                    text.append(f"⚠ Load factor {load_factor:.3f} exceeds {warn:.3f}")
            except Exception:
                pass
        self.result_view.setPlainText("\n".join(text))


__all__ = ["SnapshotInspectorPane"]
