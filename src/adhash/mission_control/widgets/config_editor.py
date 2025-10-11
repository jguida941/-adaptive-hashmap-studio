"""Schema-driven configuration editor pane."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adhash.config import AppConfig
from adhash.config_toolkit import (
    CONFIG_FIELDS,
    FieldSpec,
    apply_updates_to_config,
    format_app_config_to_toml,
    list_presets,
    load_config_document,
    load_preset,
    resolve_presets_dir,
    save_preset,
)
from adhash.contracts.error import BadInputError

from .common import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
    pyqtSignal,
)


class ConfigEditorPane(QWidget):  # type: ignore[misc]
    """Schema-driven config editor with preset management."""

    _logger = logging.getLogger(__name__)

    if pyqtSignal is not None:  # type: ignore[truthy-bool]  # noqa: SIM108
        config_saved = pyqtSignal(str)  # type: ignore[call-arg]
        config_loaded = pyqtSignal(str)  # type: ignore[call-arg]
        preset_saved = pyqtSignal(str)  # type: ignore[call-arg]
    else:  # pragma: no cover - signals only exist when Qt is available
        config_saved = None  # type: ignore[assignment]
        config_loaded = None  # type: ignore[assignment]
        preset_saved = None  # type: ignore[assignment]

    def __init__(self, parent: QWidget | None = None) -> None:  # type: ignore[override]
        super().__init__(parent)
        self.setObjectName("missionPane")
        self.setProperty("paneKind", "config")
        self._field_specs: dict[tuple[str, ...], FieldSpec] = {
            spec.path: spec for spec in CONFIG_FIELDS
        }
        self._field_widgets: dict[tuple[str, ...], Any] = {}
        self._current_config = AppConfig()
        self._config_saved_callbacks: list[Callable[[str], None]] = []
        self._config_loaded_callbacks: list[Callable[[str], None]] = []
        self._preset_saved_callbacks: list[Callable[[str], None]] = []

        layout = QVBoxLayout(self)  # type: ignore[call-arg]
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        heading = QLabel("Config Editor")  # type: ignore[call-arg]
        heading.setObjectName("paneHeading")
        layout.addWidget(heading)

        path_row = QHBoxLayout()  # type: ignore[call-arg]
        path_label = QLabel("Path:")  # type: ignore[call-arg]
        self.path_edit = QLineEdit("config/config.toml")  # type: ignore[call-arg]
        self.path_edit.setObjectName("configPathEdit")
        self.load_button = QPushButton("Load")  # type: ignore[call-arg]
        self.save_button = QPushButton("Save")  # type: ignore[call-arg]
        path_row.addWidget(path_label)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.load_button)
        path_row.addWidget(self.save_button)
        layout.addLayout(path_row)

        self.binding_label = QLabel("Config target: config/config.toml")  # type: ignore[call-arg]
        self.binding_label.setObjectName("configBindingLabel")
        self.binding_label.setWordWrap(True)  # type: ignore[attr-defined]
        layout.addWidget(self.binding_label)
        self._update_binding_label("config/config.toml")

        self.form_layout = QFormLayout()  # type: ignore[call-arg]
        self.form_layout.setContentsMargins(4, 4, 4, 4)
        for spec in CONFIG_FIELDS:
            widget = self._create_field_widget(spec)
            if spec.help_text:
                widget.setToolTip(spec.help_text)  # type: ignore[attr-defined]
            self.form_layout.addRow(spec.prompt + ":", widget)
            self._field_widgets[spec.path] = widget
        layout.addLayout(self.form_layout)

        preset_row = QHBoxLayout()  # type: ignore[call-arg]
        preset_label = QLabel("Preset:")  # type: ignore[call-arg]
        self.preset_combo = QComboBox()  # type: ignore[call-arg]
        self.preset_combo.setObjectName("presetSelector")
        self.refresh_presets_button = QPushButton("Refresh")  # type: ignore[call-arg]
        self.apply_preset_button = QPushButton("Apply")  # type: ignore[call-arg]
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.refresh_presets_button)
        preset_row.addWidget(self.apply_preset_button)
        layout.addLayout(preset_row)

        preset_save_row = QHBoxLayout()  # type: ignore[call-arg]
        self.new_preset_edit = QLineEdit()  # type: ignore[call-arg]
        self.new_preset_edit.setPlaceholderText("Preset name")  # type: ignore[attr-defined]
        self.save_preset_button = QPushButton("Save preset")  # type: ignore[call-arg]
        preset_save_row.addWidget(self.new_preset_edit, 1)
        preset_save_row.addWidget(self.save_preset_button)
        layout.addLayout(preset_save_row)

        self.status_label = QLabel("")  # type: ignore[call-arg]
        self.status_label.setObjectName("configStatusLabel")
        self.status_label.setWordWrap(True)  # type: ignore[attr-defined]
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.load_button.clicked.connect(self._on_load_clicked)  # type: ignore[attr-defined]
        self.save_button.clicked.connect(self._on_save_clicked)  # type: ignore[attr-defined]
        self.refresh_presets_button.clicked.connect(self.refresh_presets)  # type: ignore[attr-defined]
        self.apply_preset_button.clicked.connect(self._on_apply_preset)  # type: ignore[attr-defined]
        self.save_preset_button.clicked.connect(self._on_save_preset)  # type: ignore[attr-defined]

        try:
            self.presets_dir = resolve_presets_dir(None)
        except OSError:  # pragma: no cover - fallback when preset dir cannot be prepared
            fallback = Path.cwd() / "presets"
            fallback.mkdir(parents=True, exist_ok=True)
            self.presets_dir = fallback
            self._show_status(f"Using fallback preset directory: {fallback}", error=True)

        self._populate_fields(self._current_config)
        self.refresh_presets()

    def export_config(self) -> AppConfig:
        """Return the current form as a validated AppConfig."""

        return self._collect_config()

    def refresh_presets(self) -> None:
        try:
            presets = list_presets(self.presets_dir)
        except OSError as exc:  # pragma: no cover - IO issues
            self._show_status(f"Failed to list presets: {exc}", error=True)
            return
        current = (
            self.preset_combo.currentData() if hasattr(self.preset_combo, "currentData") else None
        )
        self.preset_combo.clear()
        self.preset_combo.addItem("Select preset…", userData=None)  # type: ignore[attr-defined]
        for name in presets:
            display = self._format_preset_display(name)
            self.preset_combo.addItem(display, userData=name)  # type: ignore[attr-defined]
        if current:
            index = self.preset_combo.findData(current)  # type: ignore[attr-defined]
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)

    def _create_field_widget(self, spec: FieldSpec) -> Any:
        if spec.kind == "choice" and QComboBox is not None:
            widget = QComboBox()  # type: ignore[call-arg]
            for choice in spec.choices:
                widget.addItem(choice, userData=choice)  # type: ignore[attr-defined]
            return widget
        if spec.kind == "bool" and QCheckBox is not None:
            return QCheckBox()  # type: ignore[call-arg]
        line = QLineEdit()  # type: ignore[call-arg]
        if spec.kind == "optional_float":
            line.setPlaceholderText("none")  # type: ignore[attr-defined]
        return line

    def _populate_fields(self, cfg: AppConfig) -> None:
        for spec in CONFIG_FIELDS:
            widget = self._field_widgets.get(spec.path)
            if widget is None:
                continue
            value = self._get_value(cfg, spec.path)
            if isinstance(widget, QComboBox):
                index = widget.findData(value)  # type: ignore[attr-defined]
                if index < 0:
                    widget.addItem(str(value), userData=value)  # type: ignore[attr-defined]
                    index = widget.count() - 1
                widget.setCurrentIndex(index)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))  # type: ignore[attr-defined]
            elif isinstance(widget, QLineEdit):
                if value is None:
                    widget.setText("")
                elif isinstance(value, float):
                    widget.setText(self._format_float(value))
                else:
                    widget.setText(str(value))

    def _collect_config(self) -> AppConfig:
        updates: dict[tuple[str, ...], Any] = {}
        errors: list[str] = []
        for spec, widget in self._field_widgets.items():
            try:
                updates[spec] = self._extract_widget_value(self._field_specs[spec], widget)
            except BadInputError as exc:
                errors.append(str(exc))
        if errors:
            raise BadInputError("; ".join(errors))
        cfg = apply_updates_to_config(AppConfig(), updates)
        self._current_config = cfg
        return cfg

    def _extract_widget_value(self, spec: FieldSpec, widget: Any) -> Any:
        if isinstance(widget, QComboBox):
            data = widget.currentData()  # type: ignore[attr-defined]
            return data if data is not None else widget.currentText()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()  # type: ignore[attr-defined]
        if isinstance(widget, QLineEdit):
            text = widget.text().strip()
            if spec.kind == "int":
                if not text:
                    raise BadInputError(f"{spec.prompt} cannot be empty")
                try:
                    return int(text)
                except ValueError as exc:
                    raise BadInputError(f"{spec.prompt} must be an integer") from exc
            if spec.kind == "float":
                if not text:
                    raise BadInputError(f"{spec.prompt} cannot be empty")
                try:
                    return float(text)
                except ValueError as exc:
                    raise BadInputError(f"{spec.prompt} must be numeric") from exc
            if spec.kind == "optional_float":
                if not text:
                    return None
                lowered = text.lower()
                if lowered in {"none", "null", "off", "disabled"}:
                    return None
                try:
                    return float(text)
                except ValueError as exc:
                    raise BadInputError(f"{spec.prompt} must be numeric or 'none'") from exc
            return text
        return widget

    def _on_load_clicked(self) -> None:
        path = self._get_config_path()
        try:
            cfg = load_config_document(path.resolve())
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        except (OSError, ValueError) as exc:  # pragma: no cover - unexpected IO errors
            self._show_status(f"Failed to load {path}: {exc}", error=True)
            return
        self._current_config = cfg
        self.path_edit.setText(str(path))
        self._populate_fields(cfg)
        self._update_binding_label(str(path))
        self._show_status(f"Loaded {path}")
        self._emit_config_loaded(str(path))

    def _on_save_clicked(self) -> None:
        try:
            cfg = self._collect_config()
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        path = self._get_config_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(format_app_config_to_toml(cfg), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - IO errors
            self._show_status(f"Failed to write {path}: {exc}", error=True)
            return
        self.path_edit.setText(str(path))
        self._update_binding_label(str(path))
        self._show_status(f"Saved {path}")
        self._emit_config_saved(str(path))

    def _on_apply_preset(self) -> None:
        preset = (
            self.preset_combo.currentData() if hasattr(self.preset_combo, "currentData") else None
        )
        if not preset:
            self._show_status("Select a preset to apply.", error=True)
            return
        try:
            cfg = load_preset(str(preset), self.presets_dir)
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        self._current_config = cfg
        self._populate_fields(cfg)
        self._show_status(f"Applied preset '{preset}'")

    def _on_save_preset(self) -> None:
        name = self.new_preset_edit.text().strip()
        if not name:
            self._show_status("Enter a preset name.", error=True)
            return
        try:
            cfg = self._collect_config()
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        try:
            path = save_preset(cfg, name, self.presets_dir, overwrite=True)
        except BadInputError as exc:
            self._show_status(str(exc), error=True)
            return
        self.refresh_presets()
        index = self.preset_combo.findData(path.stem)  # type: ignore[attr-defined]
        if index >= 0:
            self.preset_combo.setCurrentIndex(index)
        self._show_status(f"Preset saved to {path}")
        self._emit_preset_saved(str(path))

    def _get_config_path(self) -> Path:
        raw = self.path_edit.text().strip()
        if not raw:
            raw = "config/config.toml"
        return Path(raw).expanduser()

    @staticmethod
    def _get_value(cfg: AppConfig, path: tuple[str, ...]) -> Any:
        node: Any = cfg
        for key in path:
            node = getattr(node, key)
        return node

    @staticmethod
    def _format_float(value: float) -> str:
        text = f"{value:.6f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    @staticmethod
    def _format_preset_display(name: str) -> str:
        pretty = name.replace("_", " ").replace("-", " ")
        return pretty.title()

    def _show_status(self, message: str, *, error: bool = False) -> None:
        color = "#FF6B6B" if error else "#00FFAA"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status_label.setText(message)

    def add_config_saved_callback(self, callback: Callable[[str], None]) -> None:
        self._config_saved_callbacks.append(callback)

    def add_config_loaded_callback(self, callback: Callable[[str], None]) -> None:
        self._config_loaded_callbacks.append(callback)

    def add_preset_saved_callback(self, callback: Callable[[str], None]) -> None:
        self._preset_saved_callbacks.append(callback)

    def _update_binding_label(self, path: str) -> None:
        self.binding_label.setText(f"Config target: {path}")

    def _emit_config_saved(self, path: str) -> None:
        if self.config_saved is not None:  # type: ignore[truthy-bool]
            try:
                self.config_saved.emit(path)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover  # noqa: BLE001
                self._logger.debug("config_saved emit failed: %s", exc)
        for callback in list(self._config_saved_callbacks):
            callback(path)

    def _emit_config_loaded(self, path: str) -> None:
        if self.config_loaded is not None:  # type: ignore[truthy-bool]
            try:
                self.config_loaded.emit(path)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover  # noqa: BLE001
                self._logger.debug("config_loaded emit failed: %s", exc)
        for callback in list(self._config_loaded_callbacks):
            callback(path)

    def _emit_preset_saved(self, path: str) -> None:
        if self.preset_saved is not None:  # type: ignore[truthy-bool]
            try:
                self.preset_saved.emit(path)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover  # noqa: BLE001
                self._logger.debug("preset_saved emit failed: %s", exc)
        for callback in list(self._preset_saved_callbacks):
            callback(path)
