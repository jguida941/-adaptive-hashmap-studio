"""Coverage helper for environments with global ``sitecustomize``."""

from __future__ import annotations

import os

if os.getenv("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()
    except Exception as exc:  # pragma: no cover - defensive guard  # noqa: BLE001
        with open(".coverage_startup_error.log", "a", encoding="utf-8") as handle:
            handle.write(f"startup failure: {exc}\n")
    else:
        with open(".coverage_startup.log", "a", encoding="utf-8") as handle:
            handle.write("startup ok\n")
