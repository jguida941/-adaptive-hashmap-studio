from __future__ import annotations

from pathlib import Path

import pytest

from adhash.config import AppConfig
from adhash.config_toolkit import validate_preset_file


@pytest.fixture()
def valid_preset(tmp_path: Path) -> Path:
    preset = tmp_path / "preset.toml"
    preset.write_text(
        """
        [adaptive]
        start_backend = "robinhood"
        initial_buckets = 128
        groups_per_bucket = 8
        initial_capacity_rh = 128
        incremental_batch = 1024
        max_lf_chaining = 0.75
        max_group_len = 6
        max_avg_probe_robinhood = 5.0
        max_tombstone_ratio = 0.2
        large_map_warn_threshold = 123456

        [watchdog]
        enabled = true
        load_factor_warn = 0.8
        avg_probe_warn = 3.0
        tombstone_ratio_warn = 0.15
        """
    )
    return preset


def test_validate_preset_file_accepts_valid_preset(valid_preset: Path) -> None:
    metadata = validate_preset_file(valid_preset)
    assert metadata.adaptive.start_backend == "robinhood"
    assert metadata.adaptive.initial_buckets == 128
    assert metadata.watchdog.enabled is True
    assert metadata.watchdog.tombstone_ratio_warn == pytest.approx(0.15)


def test_validate_preset_file_rejects_invalid(tmp_path: Path) -> None:
    bad_preset = tmp_path / "bad.toml"
    bad_preset.write_text("[adaptive]\nstart_backend = 'invalid'\n")
    with pytest.raises(ValueError):
        validate_preset_file(bad_preset)


def test_validate_preset_file_handles_missing_sections(tmp_path: Path) -> None:
    empty_preset = tmp_path / "missing.toml"
    empty_preset.write_text("""
    [watchdog]
    enabled = true
    """)
    with pytest.raises(ValueError):
        validate_preset_file(empty_preset)


def test_round_trip_through_app_config(valid_preset: Path) -> None:
    metadata = validate_preset_file(valid_preset)
    cfg = AppConfig.from_dict(metadata.to_app_config_dict())
    cfg.validate()
    assert cfg.adaptive.start_backend == "robinhood"
    assert cfg.watchdog.enabled is True
