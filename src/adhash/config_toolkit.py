"""Shared helpers for interactive configuration flows.

This module centralises the schema used by the config wizard, the CLI editor,
mission control bindings, and preset management so the various entry points all
share a single source of truth.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .config import AppConfig
from .config_models import AppConfigSchema
from .contracts.error import BadInputError


@dataclass(frozen=True)
class FieldSpec:
    """Metadata describing one editable configuration value."""

    path: Tuple[str, ...]
    prompt: str
    kind: str
    choices: Tuple[str, ...] = ()
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    validator: Optional[str] = None
    help_text: str = ""


CONFIG_FIELDS: Tuple[FieldSpec, ...] = (
    FieldSpec(("adaptive", "start_backend"), "Start backend", "choice", ("chaining", "robinhood")),
    FieldSpec(
        ("adaptive", "initial_buckets"),
        "Initial buckets (power of two)",
        "int",
        validator="power_of_two",
    ),
    FieldSpec(
        ("adaptive", "groups_per_bucket"),
        "Groups per bucket (power of two)",
        "int",
        validator="power_of_two",
    ),
    FieldSpec(
        ("adaptive", "initial_capacity_rh"),
        "Initial capacity (Robin Hood, power of two)",
        "int",
        validator="power_of_two",
    ),
    FieldSpec(("adaptive", "incremental_batch"), "Incremental batch size", "int", min_value=1.0),
    FieldSpec(
        ("adaptive", "max_lf_chaining"),
        "Max load factor before migrating (0-1]",
        "float",
        min_value=0.01,
        max_value=1.0,
    ),
    FieldSpec(("adaptive", "max_group_len"), "Max chaining group length", "int", min_value=1.0),
    FieldSpec(
        ("adaptive", "max_avg_probe_robinhood"),
        "Max average probe distance (Robin Hood)",
        "float",
        min_value=0.1,
    ),
    FieldSpec(
        ("adaptive", "max_tombstone_ratio"),
        "Max tombstone ratio before compaction (0-1)",
        "float",
        min_value=0.0,
        max_value=1.0,
    ),
    FieldSpec(
        ("adaptive", "large_map_warn_threshold"),
        "Large map warning threshold (keys)",
        "int",
        min_value=0.0,
    ),
    FieldSpec(("watchdog", "enabled"), "Enable watchdog alerts", "bool"),
    FieldSpec(
        ("watchdog", "load_factor_warn"),
        "Watchdog load factor warning threshold",
        "optional_float",
        min_value=0.0,
        max_value=1.0,
    ),
    FieldSpec(
        ("watchdog", "avg_probe_warn"),
        "Watchdog avg probe warning threshold",
        "optional_float",
        min_value=0.0,
    ),
    FieldSpec(
        ("watchdog", "tombstone_ratio_warn"),
        "Watchdog tombstone ratio warning threshold",
        "optional_float",
        min_value=0.0,
        max_value=1.0,
    ),
)


DEFAULT_PRESETS_ENV = "ADHASH_PRESETS_DIR"
DEFAULT_PRESETS_DIR = Path("~/.adhash/presets").expanduser()


def _format_float(value: float) -> str:
    text = f"{value:.6f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_app_config_to_toml(cfg: AppConfig) -> str:
    adaptive = cfg.adaptive
    watchdog = cfg.watchdog
    lines = [
        "[adaptive]",
        f'start_backend = "{adaptive.start_backend}"',
        f"initial_buckets = {adaptive.initial_buckets}",
        f"groups_per_bucket = {adaptive.groups_per_bucket}",
        f"initial_capacity_rh = {adaptive.initial_capacity_rh}",
        f"incremental_batch = {adaptive.incremental_batch}",
        f"max_lf_chaining = {_format_float(adaptive.max_lf_chaining)}",
        f"max_group_len = {adaptive.max_group_len}",
        f"max_avg_probe_robinhood = {_format_float(adaptive.max_avg_probe_robinhood)}",
        f"max_tombstone_ratio = {_format_float(adaptive.max_tombstone_ratio)}",
        f"large_map_warn_threshold = {adaptive.large_map_warn_threshold}",
        "",
        "[watchdog]",
        f"enabled = {str(watchdog.enabled).lower()}",
    ]
    if watchdog.load_factor_warn is not None:
        lines.append(f"load_factor_warn = {_format_float(watchdog.load_factor_warn)}")
    else:
        lines.append('load_factor_warn = "none"')
    if watchdog.avg_probe_warn is not None:
        lines.append(f"avg_probe_warn = {_format_float(watchdog.avg_probe_warn)}")
    else:
        lines.append('avg_probe_warn = "none"')
    if watchdog.tombstone_ratio_warn is not None:
        lines.append(f"tombstone_ratio_warn = {_format_float(watchdog.tombstone_ratio_warn)}")
    else:
        lines.append('tombstone_ratio_warn = "none"')
    lines.append("")
    return "\n".join(lines)


def clone_config(cfg: AppConfig) -> AppConfig:
    """Create a deep-ish copy of ``AppConfig`` for mutation in editors."""

    return AppConfig(
        adaptive=replace(cfg.adaptive),
        watchdog=replace(cfg.watchdog),
    )


def _get_field_value(cfg: AppConfig, path: Sequence[str]) -> Any:
    node: Any = cfg
    for key in path:
        node = getattr(node, key)
    return node


def _set_field_value(cfg: AppConfig, path: Sequence[str], value: Any) -> None:
    node: Any = cfg
    for key in path[:-1]:
        node = getattr(node, key)
    setattr(node, path[-1], value)


def _validate_number_bounds(spec: FieldSpec, value: float) -> None:
    if spec.min_value is not None and value < spec.min_value:
        raise BadInputError(f"Value for {spec.prompt!r} must be ≥ {spec.min_value}")
    if spec.max_value is not None and value > spec.max_value:
        raise BadInputError(f"Value for {spec.prompt!r} must be ≤ {spec.max_value}")


def _validate_value(spec: FieldSpec, value: Any) -> None:
    kind = spec.kind
    if kind == "int":
        if not isinstance(value, int):
            raise BadInputError(f"{spec.prompt} must be an integer")
        _validate_number_bounds(spec, float(value))
    elif kind == "float":
        if not isinstance(value, (int, float)):
            raise BadInputError(f"{spec.prompt} must be numeric")
        _validate_number_bounds(spec, float(value))
    elif kind == "optional_float":
        if value is None:
            return
        if not isinstance(value, (int, float)):
            raise BadInputError(f"{spec.prompt} must be numeric or 'none'")
        _validate_number_bounds(spec, float(value))
    elif kind == "choice":
        if spec.choices and value not in spec.choices:
            raise BadInputError(f"{spec.prompt} must be one of: {', '.join(spec.choices)}")
    elif kind == "bool":
        if not isinstance(value, bool):
            raise BadInputError(f"{spec.prompt} must be true/false")

    if spec.validator == "power_of_two":
        if not isinstance(value, int) or value <= 0 or value & (value - 1) != 0:
            raise BadInputError(f"{spec.prompt} must be a power of two")


_BOOL_TRUE = {"y", "yes", "true", "1"}
_BOOL_FALSE = {"n", "no", "false", "0"}


def _parse_value(spec: FieldSpec, raw: str, current: Any) -> Any:
    text = raw.strip()
    if text == "":
        return current
    kind = spec.kind
    if kind == "choice":
        candidate = text.lower()
        for option in spec.choices:
            if candidate == option.lower():
                return option
        raise BadInputError(f"Enter one of: {', '.join(spec.choices)}")
    if kind == "int":
        try:
            value = int(text)
        except ValueError as exc:
            raise BadInputError("Enter a whole number") from exc
        return value
    if kind == "float":
        try:
            return float(text)
        except ValueError as exc:
            raise BadInputError("Enter a numeric value") from exc
    if kind == "optional_float":
        lowered = text.lower()
        if lowered in {"none", "null", "off", "disabled"}:
            return None
        try:
            return float(text)
        except ValueError as exc:
            raise BadInputError("Enter a numeric value or 'none'") from exc
    if kind == "bool":
        lowered = text.lower()
        if lowered in _BOOL_TRUE:
            return True
        if lowered in _BOOL_FALSE:
            return False
        raise BadInputError("Please answer yes or no")
    raise BadInputError(f"Unsupported field kind: {kind}")


def prompt_for_config(
    cfg: AppConfig,
    *,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> AppConfig:
    """Interactive command-line prompt that mutates and returns ``cfg``."""

    print_fn("Adaptive Hash Map Configuration Editor")
    print_fn("Press Enter to keep existing values; type 'none' to clear optional thresholds.\n")

    for spec in CONFIG_FIELDS:
        current = _get_field_value(cfg, spec.path)
        if spec.kind == "bool":
            default_hint = "Y/n" if current else "y/N"
            while True:
                raw = input_fn(f"{spec.prompt} [{default_hint}]: ")
                try:
                    value = _parse_value(spec, raw, current)
                except BadInputError as exc:
                    print_fn(str(exc))
                    continue
                _set_field_value(cfg, spec.path, value)
                break
            continue

        default_repr = (
            "none"
            if current is None
            else (
                current
                if isinstance(current, str)
                else _format_float(current) if isinstance(current, float) else str(current)
            )
        )
        if spec.choices:
            choice_hint = "/".join(spec.choices)
            prompt = f"{spec.prompt} ({choice_hint}) [{default_repr}]: "
        else:
            prompt = f"{spec.prompt} [{default_repr}]: "

        while True:
            raw = input_fn(prompt)
            try:
                value = _parse_value(spec, raw, current)
                _validate_value(spec, value)
            except BadInputError as exc:
                print_fn(str(exc))
                continue
            _set_field_value(cfg, spec.path, value)
            break

        if spec.help_text:
            print_fn(spec.help_text)

    cfg.validate()
    return cfg


def load_config_document(path: Path) -> AppConfig:
    """Load a config file without applying environment overrides."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise BadInputError(f"Config file not found: {path}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise BadInputError(f"Invalid TOML in {path}: {exc}") from exc
    cfg = AppConfig.from_dict(data if isinstance(data, dict) else {})
    cfg.validate()
    return cfg


def resolve_presets_dir(explicit: Optional[str] = None) -> Path:
    candidate = explicit or os.getenv(DEFAULT_PRESETS_ENV) or str(DEFAULT_PRESETS_DIR)
    path = Path(candidate).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


_PRESET_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def slugify_preset_name(name: str) -> str:
    slug = name.strip().lower()
    slug = _PRESET_SLUG_RE.sub("-", slug)
    slug = slug.strip("-._")
    return slug or "preset"


def list_presets(presets_dir: Path) -> List[str]:
    if not presets_dir.exists():
        return []
    entries = []
    for path in sorted(presets_dir.glob("*.toml")):
        entries.append(path.stem)
    return entries


def load_preset(name: str, presets_dir: Path) -> AppConfig:
    path = _resolve_preset_path(name, presets_dir)
    return load_config_document(path)


def validate_preset_file(path: Path) -> AppConfigSchema:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"Preset file not found: {path}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in preset {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Preset root must be a table")
    if "adaptive" not in data or "watchdog" not in data:
        raise ValueError("Preset must define [adaptive] and [watchdog] sections")

    try:
        cfg = AppConfig.from_dict(data)
        cfg.validate()
    except Exception as exc:  # pragma: no cover - rewrap config validation errors
        raise ValueError(f"Preset validation failed: {exc}") from exc

    return AppConfigSchema.from_app_config(cfg)


def save_preset(
    cfg: AppConfig,
    name: str,
    presets_dir: Path,
    *,
    overwrite: bool = False,
) -> Path:
    slug = slugify_preset_name(name)
    presets_dir.mkdir(parents=True, exist_ok=True)
    path = presets_dir / f"{slug}.toml"
    if path.exists() and not overwrite:
        raise BadInputError(f"Preset {slug!r} already exists (use --force to overwrite)")
    path.write_text(format_app_config_to_toml(cfg), encoding="utf-8")
    return path


def _resolve_preset_path(name: str, presets_dir: Path) -> Path:
    candidate = Path(name)
    if (candidate.is_absolute() or candidate.parent != Path(".")) and candidate.exists():
        return candidate
    if candidate.suffix == ".toml" and candidate.exists():
        return candidate
    slug = slugify_preset_name(name)
    path = presets_dir / f"{slug}.toml"
    if not path.exists():
        raise BadInputError(f"Preset {slug!r} not found in {presets_dir}")
    return path


def apply_updates_to_config(cfg: AppConfig, updates: Dict[Tuple[str, ...], Any]) -> AppConfig:
    clone = clone_config(cfg)
    for path, value in updates.items():
        spec = next((item for item in CONFIG_FIELDS if item.path == path), None)
        if spec is None:
            raise BadInputError(f"Unknown config path: {'.'.join(path)}")
        _validate_value(spec, value)
        _set_field_value(clone, path, value)
    clone.validate()
    return clone


__all__ = [
    "CONFIG_FIELDS",
    "FieldSpec",
    "apply_updates_to_config",
    "clone_config",
    "format_app_config_to_toml",
    "list_presets",
    "load_config_document",
    "load_preset",
    "validate_preset_file",
    "prompt_for_config",
    "resolve_presets_dir",
    "save_preset",
    "slugify_preset_name",
]
