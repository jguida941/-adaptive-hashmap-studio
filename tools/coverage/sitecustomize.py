"""Coverage helper to enable subprocess measurement."""

from __future__ import annotations

import os


if os.getenv("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()
    except Exception:  # pragma: no cover - defensive guard
        pass
