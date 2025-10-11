from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, cast

try:
    from hypothesis import HealthCheck as _HealthCheck
    from hypothesis import Phase as _Phase
    from hypothesis import settings as _settings
except ModuleNotFoundError:  # pragma: no cover - optional dependency

    class _DummyHealthCheck:
        too_slow = "too_slow"
        filter_too_much = "filter_too_much"

    class _DummyPhase:
        explicit = "explicit"
        reuse = "reuse"
        generate = "generate"
        target = "target"

    class _DummySettings:
        def register_profile(self, *_args: object, **_kwargs: object) -> None:
            """Stub hook used when Hypothesis is unavailable."""
            return

        def load_profile(self, *_args: object, **_kwargs: object) -> None:
            """Stub hook used when Hypothesis is unavailable."""
            return

    HealthCheck = cast(Any, _DummyHealthCheck())
    Phase = cast(Any, _DummyPhase())
    settings = cast(Any, _DummySettings())
else:
    HealthCheck = _HealthCheck
    Phase = _Phase
    settings = _settings

# Shared default: deterministic-ish runs with moderate deadlines.
settings.register_profile(
    "default",
    max_examples=50,
    deadline=timedelta(milliseconds=500),
    derandomize=True,
    print_blob=True,
)

# Local development: faster feedback with reasonable deadlines.
settings.register_profile(
    "dev",
    max_examples=75,
    deadline=timedelta(milliseconds=200),
    suppress_health_check=[HealthCheck.too_slow],
    phases=(Phase.explicit, Phase.reuse, Phase.generate, Phase.target),
)

# Continuous integration: deterministic, thorough, and blob-friendly output.
settings.register_profile(
    "ci",
    max_examples=200,
    deadline=None,
    print_blob=True,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    phases=(Phase.explicit, Phase.reuse, Phase.generate, Phase.target),
)

default_profile = os.getenv("HYPOTHESIS_PROFILE", "default")
try:
    settings.load_profile(default_profile)
except KeyError:  # pragma: no cover - defensive guard
    settings.load_profile("default")

__all__ = ["default_profile"]
