from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .config import AppConfig


@dataclass(frozen=True)
class AdaptiveConfigModel:
    start_backend: str
    initial_buckets: int
    groups_per_bucket: int
    initial_capacity_rh: int
    incremental_batch: int
    max_lf_chaining: float
    max_group_len: int
    max_avg_probe_robinhood: float
    max_tombstone_ratio: float
    large_map_warn_threshold: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_backend": self.start_backend,
            "initial_buckets": self.initial_buckets,
            "groups_per_bucket": self.groups_per_bucket,
            "initial_capacity_rh": self.initial_capacity_rh,
            "incremental_batch": self.incremental_batch,
            "max_lf_chaining": self.max_lf_chaining,
            "max_group_len": self.max_group_len,
            "max_avg_probe_robinhood": self.max_avg_probe_robinhood,
            "max_tombstone_ratio": self.max_tombstone_ratio,
            "large_map_warn_threshold": self.large_map_warn_threshold,
        }


@dataclass(frozen=True)
class WatchdogConfigModel:
    enabled: bool
    load_factor_warn: Optional[float]
    avg_probe_warn: Optional[float]
    tombstone_ratio_warn: Optional[float]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "load_factor_warn": self.load_factor_warn,
            "avg_probe_warn": self.avg_probe_warn,
            "tombstone_ratio_warn": self.tombstone_ratio_warn,
        }


@dataclass(frozen=True)
class AppConfigSchema:
    adaptive: AdaptiveConfigModel
    watchdog: WatchdogConfigModel

    def to_app_config_dict(self) -> Dict[str, Any]:
        return {
            "adaptive": self.adaptive.to_dict(),
            "watchdog": self.watchdog.to_dict(),
        }

    def to_app_config(self) -> AppConfig:
        cfg = AppConfig.from_dict(self.to_app_config_dict())
        cfg.validate()
        return cfg

    @classmethod
    def from_app_config(cls, cfg: AppConfig) -> "AppConfigSchema":
        adaptive = cfg.adaptive
        watchdog = cfg.watchdog
        return cls(
            adaptive=AdaptiveConfigModel(
                start_backend=adaptive.start_backend,
                initial_buckets=adaptive.initial_buckets,
                groups_per_bucket=adaptive.groups_per_bucket,
                initial_capacity_rh=adaptive.initial_capacity_rh,
                incremental_batch=adaptive.incremental_batch,
                max_lf_chaining=adaptive.max_lf_chaining,
                max_group_len=adaptive.max_group_len,
                max_avg_probe_robinhood=adaptive.max_avg_probe_robinhood,
                max_tombstone_ratio=adaptive.max_tombstone_ratio,
                large_map_warn_threshold=adaptive.large_map_warn_threshold,
            ),
            watchdog=WatchdogConfigModel(
                enabled=watchdog.enabled,
                load_factor_warn=watchdog.load_factor_warn,
                avg_probe_warn=watchdog.avg_probe_warn,
                tombstone_ratio_warn=watchdog.tombstone_ratio_warn,
            ),
        )
