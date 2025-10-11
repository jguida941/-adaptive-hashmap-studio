#!/usr/bin/env python3
"""Generate or refresh the Ruff lint baseline.

This script captures the current Ruff diagnostics and writes them to
``.ruff_baseline.json`` so the unified pipeline can enforce a
``no-new-lint`` policy while we work through the backlog.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # noqa: S404  # nosec B404 - local CLI helper, command args are curated
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUFF_BASELINE_PATH = PROJECT_ROOT / ".ruff_baseline.json"


def _candidate_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    venv_ruff = PROJECT_ROOT / ".venv" / "bin" / "ruff"
    if venv_ruff.exists():
        commands.append([str(venv_ruff)])
    if shutil.which("ruff"):
        commands.append(["ruff"])
    if shutil.which("uv"):
        commands.append(["uv", "run", "ruff"])
    return commands


def _run_ruff(cmd: Sequence[str]) -> list[dict[str, Any]]:
    args = [
        *cmd,
        "check",
        ".",
        "--force-exclude",
        "--respect-gitignore",
        "--output-format=json",
        "--exit-zero",
    ]
    env = os.environ.copy()
    # Avoid hitting read-only cache directories when running under sandboxed shells.
    env.setdefault("UV_CACHE_DIR", str(PROJECT_ROOT / ".uv_cache"))
    proc = subprocess.run(  # noqa: S603  # nosec B603 - arguments built from internal ruff config
        args,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
    )
    diagnostics = json.loads(proc.stdout)
    return cast(list[dict[str, Any]], diagnostics)


def _select_command() -> list[str]:
    for cmd in _candidate_commands():
        try:
            env = os.environ.copy()
            env.setdefault("UV_CACHE_DIR", str(PROJECT_ROOT / ".uv_cache"))
            subprocess.run(  # noqa: S603  # nosec B603 - version probe for known binaries
                [*cmd, "--version"],
                check=True,
                capture_output=True,
                cwd=PROJECT_ROOT,
                env=env,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        else:
            return list(cmd)
    # Fall back to first candidate and let the actual run raise a clearer error.
    candidates = _candidate_commands()
    if not candidates:
        raise RuntimeError(
            "Could not find a Ruff executable (expected .venv/bin/ruff, ruff, or uv run ruff)."
        )
    return candidates[0]


def _collect_diagnostics() -> list[dict[str, Any]]:
    cmd = _select_command()
    return _run_ruff(cmd)


def _diag_key(entry: dict[str, Any]) -> str:
    filename = Path(entry["filename"]).resolve()
    try:
        rel = filename.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = filename
    location = entry.get("location") or {}
    return f"{rel.as_posix()}:{location.get('row')}:{location.get('column')}:{entry.get('code')}"


def main() -> int:
    diagnostics = _collect_diagnostics()
    keys = sorted({_diag_key(entry) for entry in diagnostics})
    payload = {
        "version": 1,
        "generated": keys,
    }
    RUFF_BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf8")
    print(f"Wrote {len(keys)} Ruff diagnostics to {RUFF_BASELINE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
