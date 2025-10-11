from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adhash.config import AdaptivePolicy, AppConfig, WatchdogPolicy
from adhash.contracts.error import BadInputError


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"start_backend": "linear"}, "adaptive.start_backend"),
        ({"initial_buckets": 3}, "adaptive.initial_buckets"),
        ({"groups_per_bucket": 0}, "adaptive.groups_per_bucket"),
        ({"initial_capacity_rh": 5}, "adaptive.initial_capacity_rh"),
        ({"incremental_batch": 0}, "adaptive.incremental_batch"),
        ({"max_lf_chaining": 1.5}, "adaptive.max_lf_chaining"),
        ({"max_lf_chaining": 0.0}, "adaptive.max_lf_chaining"),
        ({"max_group_len": 0}, "adaptive.max_group_len"),
        ({"max_avg_probe_robinhood": 0.0}, "adaptive.max_avg_probe_robinhood"),
        ({"max_tombstone_ratio": 1.5}, "adaptive.max_tombstone_ratio"),
        ({"max_tombstone_ratio": -0.1}, "adaptive.max_tombstone_ratio"),
        ({"large_map_warn_threshold": -1}, "adaptive.large_map_warn_threshold"),
    ],
)
def test_adaptive_policy_validate_rejects_invalid_values(
    updates: dict[str, Any], message: str
) -> None:
    policy = AdaptivePolicy(**updates)
    with pytest.raises(BadInputError) as exc:
        policy.validate()
    assert message in str(exc.value)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"load_factor_warn": 1.5}, "watchdog.load_factor_warn"),
        ({"avg_probe_warn": 0.0}, "watchdog.avg_probe_warn"),
        ({"tombstone_ratio_warn": 2.0}, "watchdog.tombstone_ratio_warn"),
        ({"tombstone_ratio_warn": -0.1}, "watchdog.tombstone_ratio_warn"),
    ],
)
def test_watchdog_policy_rejects_out_of_range_values(updates: dict[str, Any], message: str) -> None:
    policy = WatchdogPolicy(**updates)
    with pytest.raises(BadInputError) as exc:
        policy.validate()
    assert message in str(exc.value)


def test_app_config_from_dict_coerces_strings() -> None:
    cfg = AppConfig.from_dict(
        {
            "adaptive": {"initial_buckets": 128},
            "watchdog": {
                "enabled": " off ",
                "load_factor_warn": "0.7",
                "avg_probe_warn": "none",
                "tombstone_ratio_warn": "disabled",
            },
        }
    )
    assert cfg.adaptive.initial_buckets == 128
    assert cfg.watchdog.enabled is False
    assert cfg.watchdog.load_factor_warn == pytest.approx(0.7)
    assert cfg.watchdog.avg_probe_warn is None
    assert cfg.watchdog.tombstone_ratio_warn is None


def test_app_config_from_dict_validates_sections() -> None:
    with pytest.raises(BadInputError):
        AppConfig.from_dict({"adaptive": []})
    with pytest.raises(BadInputError):
        AppConfig.from_dict({"watchdog": []})


def test_app_config_from_dict_validates_watchdog_payloads() -> None:
    data = {
        "watchdog": {"enabled": "definitely"},
    }
    with pytest.raises(BadInputError):
        AppConfig.from_dict(data)

    data = {
        "watchdog": {"load_factor_warn": "not a number"},
    }
    with pytest.raises(BadInputError):
        AppConfig.from_dict(data)


def test_app_config_from_dict_truthy_enabled_and_none_values() -> None:
    cfg = AppConfig.from_dict(
        {
            "watchdog": {
                "enabled": "YES",
                "avg_probe_warn": None,
            }
        }
    )
    assert cfg.watchdog.enabled is True
    assert cfg.watchdog.avg_probe_warn is None


def test_app_config_apply_env_overrides_sets_values() -> None:
    cfg = AppConfig()
    env = {
        "ADAPTIVE_INITIAL_BUCKETS": "512",
        "ADAPTIVE_MAX_LF_CHAINING": "0.6",
        "WATCHDOG_ENABLED": "yes",
        "WATCHDOG_LOAD_FACTOR_WARN": "0.8",
        "WATCHDOG_AVG_PROBE_WARN": "3.5",
    }
    cfg.apply_env_overrides(env)
    assert cfg.adaptive.initial_buckets == 512
    assert cfg.adaptive.max_lf_chaining == pytest.approx(0.6)
    assert cfg.watchdog.enabled is True
    assert cfg.watchdog.load_factor_warn == pytest.approx(0.8)
    assert cfg.watchdog.avg_probe_warn == pytest.approx(3.5)


def test_app_config_apply_env_overrides_invalid_values() -> None:
    cfg = AppConfig()
    with pytest.raises(BadInputError):
        cfg.apply_env_overrides({"ADAPTIVE_INITIAL_BUCKETS": "not-int"})
    with pytest.raises(BadInputError):
        cfg.apply_env_overrides({"WATCHDOG_ENABLED": "definitely"})
    with pytest.raises(BadInputError):
        cfg.apply_env_overrides({"WATCHDOG_LOAD_FACTOR_WARN": "oops"})


def test_app_config_load_handles_missing_and_invalid(tmp_path: Path) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(BadInputError):
        AppConfig.load(missing)

    bad_toml = tmp_path / "invalid.toml"
    bad_toml.write_text("this is not = toml", encoding="utf-8")
    with pytest.raises(BadInputError):
        AppConfig.load(bad_toml)
