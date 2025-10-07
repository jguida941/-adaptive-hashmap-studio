"""Coverage helper for environments with global ``sitecustomize``."""

from __future__ import annotations

import os


if os.getenv("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive guard
        with open(".coverage_startup_error.log", "a", encoding="utf-8") as handle:
            handle.write("startup failure\n")
    else:
        with open(".coverage_startup.log", "a", encoding="utf-8") as handle:
            handle.write("startup ok\n")
