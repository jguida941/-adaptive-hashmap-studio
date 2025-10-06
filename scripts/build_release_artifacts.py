"""Build local release artifacts with checksums and a lightweight SBOM."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def _load_pyproject() -> Dict[str, Any]:
    import tomllib

    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _ensure_build_installed() -> None:
    try:
        import build  # noqa: F401  # pragma: no cover
    except ImportError:  # pragma: no cover - only executed when module missing
        subprocess.run([sys.executable, "-m", "pip", "install", "build>=1.2"], check=True)


def _run_build(outdir: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "build",
        "--wheel",
        "--sdist",
        "--outdir",
        str(outdir),
    ]
    subprocess.run(cmd, check=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksums(outdir: Path) -> None:
    sha_path = outdir / "SHA256SUMS.txt"
    with sha_path.open("w", encoding="utf-8") as handle:
        for artifact in sorted(outdir.iterdir()):
            if artifact.name == "SHA256SUMS.txt":
                continue
            digest = _sha256(artifact)
            handle.write(f"{digest}  {artifact.name}\n")


def _write_sbom(outdir: Path, metadata: Dict[str, Any]) -> None:
    packages: List[Dict[str, Any]] = []
    project_name = metadata.get("project", {}).get("name", "adaptive-hashmap-cli")
    version = metadata.get("project", {}).get("version", "0.0.0")
    deps = metadata.get("project", {}).get("dependencies", [])
    extras = metadata.get("project", {}).get("optional-dependencies", {})

    packages.append(
        {
            "name": project_name,
            "version": version,
            "dependencies": deps,
            "extras": extras,
        }
    )

    artifacts = []
    for artifact in sorted(outdir.iterdir()):
        if artifact.name == "SHA256SUMS.txt":
            continue
        artifacts.append(
            {
                "file": artifact.name,
                "size": artifact.stat().st_size,
                "sha256": _sha256(artifact),
            }
        )

    sbom = {
        "schema": "adhash.sbom.v1",
        "generated_at": time.time(),
        "packages": packages,
        "artifacts": artifacts,
        "source": "scripts/build_release_artifacts.py",
    }

    (outdir / "source-sbom.spdx.json").write_text(
        json.dumps(sbom, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build release artifacts locally.")
    parser.add_argument("--outdir", default="dist", help="Output directory (default: dist)")
    args = parser.parse_args()

    outdir = Path(args.outdir).expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    metadata = _load_pyproject()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _ensure_build_installed()
        _run_build(tmp_dir)
        for artifact in tmp_dir.iterdir():
            shutil.move(str(artifact), outdir / artifact.name)

    _write_checksums(outdir)
    _write_sbom(outdir, metadata)
    print(f"Artifacts written to {outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
