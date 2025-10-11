"""Typed configuration loader for Adaptive Hash Map CLI."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts.error import BadInputError


@dataclass
class AdaptivePolicy:
    start_backend: str = "chaining"
    initial_buckets: int = 64
    groups_per_bucket: int = 8
    initial_capacity_rh: int = 64
    incremental_batch: int = 2048
    max_lf_chaining: float = 0.82
    max_group_len: int = 8
    max_avg_probe_robinhood: float = 6.0
    max_tombstone_ratio: float = 0.25
    large_map_warn_threshold: int = 1_000_000

    def validate(self) -> None:
        if self.start_backend not in {"chaining", "robinhood"}:
            raise BadInputError("adaptive.start_backend must be 'chaining' or 'robinhood'")
        for name in ("initial_buckets", "groups_per_bucket", "initial_capacity_rh"):
            value = getattr(self, name)
            if value <= 0 or (value & (value - 1)) != 0:
                raise BadInputError(f"adaptive.{name} must be a power of two > 0")
        if self.incremental_batch <= 0:
            raise BadInputError("adaptive.incremental_batch must be > 0")
        if not 0.0 < self.max_lf_chaining <= 1.0:
            raise BadInputError("adaptive.max_lf_chaining must be in (0, 1]")
        if self.max_group_len <= 0:
            raise BadInputError("adaptive.max_group_len must be > 0")
        if self.max_avg_probe_robinhood <= 0:
            raise BadInputError("adaptive.max_avg_probe_robinhood must be > 0")
        if not 0.0 <= self.max_tombstone_ratio <= 1.0:
            raise BadInputError("adaptive.max_tombstone_ratio must be in [0, 1]")
        if self.large_map_warn_threshold < 0:
            raise BadInputError("adaptive.large_map_warn_threshold must be >= 0")


@dataclass
class WatchdogPolicy:
    enabled: bool = True
    load_factor_warn: float | None = 0.9
    avg_probe_warn: float | None = 8.0
    tombstone_ratio_warn: float | None = 0.35

    def validate(self) -> None:
        if self.load_factor_warn is not None and not 0.0 <= self.load_factor_warn <= 1.0:
            raise BadInputError("watchdog.load_factor_warn must be within [0, 1]")
        if self.avg_probe_warn is not None and self.avg_probe_warn <= 0.0:
            raise BadInputError("watchdog.avg_probe_warn must be > 0 when set")
        if self.tombstone_ratio_warn is not None and not 0.0 <= self.tombstone_ratio_warn <= 1.0:
            raise BadInputError("watchdog.tombstone_ratio_warn must be within [0, 1]")


@dataclass
class AppConfig:
    adaptive: AdaptivePolicy = field(default_factory=AdaptivePolicy)
    watchdog: WatchdogPolicy = field(default_factory=WatchdogPolicy)

    @classmethod
    def load(cls, path: Path | None) -> AppConfig:
        if path is None:
            cfg = cls()
        else:
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError as exc:
                raise BadInputError(f"Config file not found: {path}") from exc
            except tomllib.TOMLDecodeError as exc:
                raise BadInputError(f"Invalid TOML: {exc}") from exc
            cfg = cls.from_dict(data)
        cfg.apply_env_overrides(os.environ)
        cfg.validate()
        return cfg

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        adaptive_data = data.get("adaptive", {})
        if not isinstance(adaptive_data, dict):
            raise BadInputError("[adaptive] section must be a table")
        adaptive = AdaptivePolicy(**adaptive_data)
        watchdog_data = data.get("watchdog", {})
        if not isinstance(watchdog_data, dict):
            raise BadInputError("[watchdog] section must be a table")
        watchdog_kwargs: dict[str, Any] = {}

        if "enabled" in watchdog_data:
            raw_enabled = watchdog_data["enabled"]
            if isinstance(raw_enabled, str):
                normalized = raw_enabled.strip().lower()
                if normalized in {"1", "true", "yes", "on"}:
                    watchdog_kwargs["enabled"] = True
                elif normalized in {"0", "false", "no", "off"}:
                    watchdog_kwargs["enabled"] = False
                else:
                    raise BadInputError("watchdog.enabled must be boolean")
            else:
                watchdog_kwargs["enabled"] = bool(raw_enabled)

        def coerce_optional_float(key: str) -> None:
            if key not in watchdog_data:
                return
            value = watchdog_data[key]
            if isinstance(value, str):
                normalized = value.strip().lower()
                if normalized in {"none", "null", "disabled", "off"}:
                    watchdog_kwargs[key] = None
                    return
            if value is None:
                watchdog_kwargs[key] = None
                return
            try:
                watchdog_kwargs[key] = float(value)
            except (TypeError, ValueError) as exc:
                raise BadInputError(f"watchdog.{key} must be a number or 'none'") from exc

        coerce_optional_float("load_factor_warn")
        coerce_optional_float("avg_probe_warn")
        coerce_optional_float("tombstone_ratio_warn")

        watchdog = WatchdogPolicy(**watchdog_kwargs)
        return cls(adaptive=adaptive, watchdog=watchdog)

    def apply_env_overrides(self, env: Mapping[str, str]) -> None:
        adaptive_mapping: dict[str, tuple[str, Callable[[str], Any]]] = {
            "ADAPTIVE_START_BACKEND": ("start_backend", str),
            "ADAPTIVE_INITIAL_BUCKETS": ("initial_buckets", int),
            "ADAPTIVE_GROUPS_PER_BUCKET": ("groups_per_bucket", int),
            "ADAPTIVE_INITIAL_CAPACITY_RH": ("initial_capacity_rh", int),
            "ADAPTIVE_INCREMENTAL_BATCH": ("incremental_batch", int),
            "ADAPTIVE_MAX_LF_CHAINING": ("max_lf_chaining", float),
            "ADAPTIVE_MAX_GROUP_LEN": ("max_group_len", int),
            "ADAPTIVE_MAX_AVG_PROBE_RH": ("max_avg_probe_robinhood", float),
            "ADAPTIVE_MAX_TOMBSTONE_RATIO": ("max_tombstone_ratio", float),
            "ADAPTIVE_LARGE_WARN_THRESHOLD": ("large_map_warn_threshold", int),
        }
        for key, (attr, caster) in adaptive_mapping.items():
            raw_value = env.get(key)
            if raw_value is None:
                continue
            try:
                value = caster(raw_value)
            except ValueError as exc:
                raise BadInputError(f"Invalid env override {key}={raw_value!r}") from exc
            setattr(self.adaptive, attr, value)

        raw_enabled = env.get("WATCHDOG_ENABLED")
        if raw_enabled is not None:
            normalized = raw_enabled.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                self.watchdog.enabled = True
            elif normalized in {"0", "false", "no", "off"}:
                self.watchdog.enabled = False
            else:
                raise BadInputError(f"Invalid env override WATCHDOG_ENABLED={raw_enabled!r}")

        float_overrides: dict[str, str] = {
            "WATCHDOG_LOAD_FACTOR_WARN": "load_factor_warn",
            "WATCHDOG_AVG_PROBE_WARN": "avg_probe_warn",
            "WATCHDOG_TOMBSTONE_WARN": "tombstone_ratio_warn",
        }
        for key, attr in float_overrides.items():
            raw_value = env.get(key)
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
            except ValueError as exc:
                raise BadInputError(f"Invalid env override {key}={raw_value!r}") from exc
            setattr(self.watchdog, attr, value)

    def validate(self) -> None:
        self.adaptive.validate()
        self.watchdog.validate()


DEFAULT_CONFIG = AppConfig()


def load_app_config(path: str | None) -> AppConfig:
    config_path = Path(path) if path else None
    return AppConfig.load(config_path)
