"""Coverage helper to enable subprocess measurement."""

from __future__ import annotations

import os
import sys

if os.getenv("COVERAGE_PROCESS_START"):
    try:
        import coverage

        coverage.process_startup()
    except Exception as exc:  # pragma: no cover - defensive guard  # noqa: BLE001
        sys.stderr.write(f"[coverage] startup failed: {exc}\n")
