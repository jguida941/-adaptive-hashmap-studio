from __future__ import annotations

import os
from datetime import timedelta

from hypothesis import HealthCheck, Phase, settings

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

default_profile = os.getenv("HYPOTHESIS_PROFILE", "dev")
settings.load_profile(default_profile)

__all__ = ["default_profile"]
