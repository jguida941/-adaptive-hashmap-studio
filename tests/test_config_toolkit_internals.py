from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from adhash.config import AdaptivePolicy, AppConfig
from adhash.config_toolkit import (
    CONFIG_FIELDS,
    FieldSpec,
    _format_float,
    _set_field_value,
    _validate_number_bounds,
    _validate_value,
    apply_updates_to_config,
    clone_config,
    format_app_config_to_toml,
    list_presets,
    save_preset,
    slugify_preset_name,
    validate_preset_file,
)
from adhash.contracts.error import BadInputError


def _get_spec(path: tuple[str, ...]) -> FieldSpec:
    for spec in CONFIG_FIELDS:
        if spec.path == path:
            return spec
    raise AssertionError(f"FieldSpec not found for path {path}")


def test_format_float_strips_trailing_zeroes() -> None:
    assert _format_float(1.230000) == "1.23"
    assert _format_float(3.0) == "3"
    assert _format_float(0.000001) == "0.000001"


def test_validate_number_bounds_respects_limits() -> None:
    spec = FieldSpec(
        ("watchdog", "load_factor_warn"),
        "Load factor",
        "float",
        min_value=0.0,
        max_value=1.0,
    )
    _validate_number_bounds(spec, 0.0)
    _validate_number_bounds(spec, 1.0)
    with pytest.raises(BadInputError):
        _validate_number_bounds(spec, -0.01)
    with pytest.raises(BadInputError):
        _validate_number_bounds(spec, 1.5)


def test_validate_value_optional_float_accepts_none_and_numbers() -> None:
    spec = FieldSpec(("watchdog", "avg_probe_warn"), "Probe warn", "optional_float", min_value=0.0)
    _validate_value(spec, None)
    _validate_value(spec, 0)
    _validate_value(spec, 1.234)
    with pytest.raises(BadInputError):
        _validate_value(spec, -1)
    with pytest.raises(BadInputError):
        _validate_value(spec, "oops")


def test_set_field_value_updates_nested_dataclass() -> None:
    cfg = clone_config(AppConfig())
    spec = _get_spec(("adaptive", "max_avg_probe_robinhood"))
    assert math.isclose(cfg.adaptive.max_avg_probe_robinhood, 6.0, rel_tol=1e-9)
    _set_field_value(cfg, spec.path, 7.5)
    assert math.isclose(cfg.adaptive.max_avg_probe_robinhood, 7.5, rel_tol=1e-9)


def test_clone_config_returns_independent_objects() -> None:
    cfg = AppConfig()
    clone = clone_config(cfg)
    assert clone is not cfg
    assert clone.adaptive is not cfg.adaptive

    spec = _get_spec(("adaptive", "initial_buckets"))
    original_value = cfg.adaptive.initial_buckets
    updated_value = original_value * 4
    _set_field_value(clone, spec.path, updated_value)

    assert clone.adaptive.initial_buckets == updated_value
    assert cfg.adaptive.initial_buckets == original_value


def test_format_app_config_to_toml_contains_sections() -> None:
    cfg = AppConfig()
    rendered = format_app_config_to_toml(cfg)
    assert "[adaptive]" in rendered
    assert "[watchdog]" in rendered
    # ensure floats are stripped correctly
    assert "max_avg_probe_robinhood" in rendered


def test_apply_updates_to_config_accepts_valid_updates() -> None:
    cfg = AppConfig()
    updates: dict[tuple[str, ...], Any] = {
        ("adaptive", "incremental_batch"): cfg.adaptive.incremental_batch + 128,
        ("watchdog", "enabled"): False,
    }
    updated = apply_updates_to_config(cfg, updates)
    assert updated.adaptive.incremental_batch == cfg.adaptive.incremental_batch + 128
    assert updated.watchdog.enabled is False


def test_apply_updates_to_config_rejects_unknown_path() -> None:
    cfg = AppConfig()
    with pytest.raises(BadInputError):
        apply_updates_to_config(cfg, {("adaptive", "unknown"): 1})


def test_save_and_load_preset_round_trip(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.adaptive = AdaptivePolicy(start_backend="robinhood", initial_buckets=256)
    save_path = save_preset(cfg, "My Preset", tmp_path)
    assert save_path.exists()

    presets = list_presets(tmp_path)
    assert slugify_preset_name("My Preset") in presets

    schema = validate_preset_file(save_path)
    loaded_cfg = schema.to_app_config()
    assert loaded_cfg.adaptive.start_backend == "robinhood"
    assert loaded_cfg.adaptive.initial_buckets == 256
