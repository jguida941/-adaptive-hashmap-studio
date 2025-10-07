"""Coverage helper to enable subprocess measurement."""

from __future__ import annotations

import os


if os.getenv("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive guard
        pass
