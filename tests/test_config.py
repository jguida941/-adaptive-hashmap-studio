from __future__ import annotations

from pathlib import Path

import pytest

from adhash.config import AppConfig, load_app_config
from adhash.contracts.error import BadInputError


def test_default_config_validates() -> None:
    cfg = load_app_config(None)
    assert cfg.adaptive.start_backend == "chaining"
    assert cfg.adaptive.initial_buckets == 64
    assert cfg.watchdog.enabled is True
    assert cfg.watchdog.load_factor_warn == pytest.approx(0.9)


def test_load_from_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        """
[adaptive]
start_backend = "robinhood"
initial_buckets = 128
groups_per_bucket = 4
initial_capacity_rh = 256
incremental_batch = 4096
max_lf_chaining = 0.7
max_group_len = 6
max_avg_probe_robinhood = 5.5
max_tombstone_ratio = 0.2
large_map_warn_threshold = 200000

[watchdog]
enabled = true
load_factor_warn = 0.88
avg_probe_warn = 7.5
tombstone_ratio_warn = 0.3
""",
        encoding="utf-8",
    )
    cfg = load_app_config(str(cfg_path))
    adaptive = cfg.adaptive
    assert adaptive.start_backend == "robinhood"
    assert adaptive.initial_buckets == 128
    assert adaptive.max_lf_chaining == 0.7
    watchdog = cfg.watchdog
    assert watchdog.enabled is True
    assert watchdog.load_factor_warn == pytest.approx(0.88)
    assert watchdog.avg_probe_warn == pytest.approx(7.5)
    assert watchdog.tombstone_ratio_warn == pytest.approx(0.3)

    # env override takes precedence
    monkeypatch.setenv("ADAPTIVE_MAX_GROUP_LEN", "12")
    monkeypatch.setenv("WATCHDOG_ENABLED", "false")
    monkeypatch.setenv("WATCHDOG_TOMBSTONE_WARN", "0.4")
    cfg_env = AppConfig.load(cfg_path)
    assert cfg_env.adaptive.max_group_len == 12
    assert cfg_env.watchdog.enabled is False
    assert cfg_env.watchdog.tombstone_ratio_warn == pytest.approx(0.4)


def test_invalid_values_raise(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.toml"
    bad_path.write_text("[adaptive]\nmax_lf_chaining = 1.5\n", encoding="utf-8")
    with pytest.raises(BadInputError):
        load_app_config(str(bad_path))

    bad_watchdog = tmp_path / "bad_watchdog.toml"
    bad_watchdog.write_text("[watchdog]\nload_factor_warn = 1.5\n", encoding="utf-8")
    with pytest.raises(BadInputError):
        load_app_config(str(bad_watchdog))
