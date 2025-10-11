#!/usr/bin/env python3
"""Fail-fast guard against unsafe subprocess patterns."""

from __future__ import annotations

import re
from pathlib import Path

ROOTS = ("src", "scripts")
ALLOW_FILES = {
    "src/adhash/_safe_subprocess.py",
}
PATTERN_SHELL_TRUE = re.compile(
    r"subprocess\.run\([^)]*shell\s*=\s*True", re.IGNORECASE | re.DOTALL
)
PATTERN_STRING_ARGS = re.compile(r"subprocess\.run\(\s*[\"']", re.DOTALL)


def _should_skip(path: Path) -> bool:
    rel = path.as_posix()
    if rel in ALLOW_FILES:
        return True
    return bool(rel.startswith("tests/") or "/tests/" in rel)


def _check_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    hits: list[str] = []
    rel = path.as_posix()
    if PATTERN_SHELL_TRUE.search(text):
        hits.append("shell=True")
    if rel not in ALLOW_FILES and PATTERN_STRING_ARGS.search(text):
        hits.append("string-command")
    return hits


def main() -> int:
    failures: list[tuple[str, list[str]]] = []
    for root in ROOTS:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for file_path in root_path.rglob("*.py"):
            if _should_skip(file_path):
                continue
            issues = _check_file(file_path)
            if issues:
                failures.append((file_path.as_posix(), issues))
    if failures:
        print("❌ Unsafe subprocess usage detected:")
        for rel, issues in failures:
            print(f"  - {rel}: {', '.join(issues)}")
        print("Use adhash._safe_subprocess.safe_run/safe_popen and avoid shell=True.")
        return 2
    print("✅ Subprocess safety checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
