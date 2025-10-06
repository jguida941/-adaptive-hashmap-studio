"""Mission Control public exports."""

from __future__ import annotations

__all__ = [
    "build_app",
    "build_controller",
    "build_widgets",
    "build_window",
    "MissionControlController",
    "run_mission_control",
]


def __getattr__(name: str):  # pragma: no cover - thin re-export shim
    if name == "run_mission_control":
        from .app import run_mission_control as func

        return func
    if name in {"build_app", "build_controller", "build_widgets", "build_window"}:
        from . import builders

        return getattr(builders, name)
    if name == "MissionControlController":
        from .controller import MissionControlController as cls

        return cls
    raise AttributeError(name)
