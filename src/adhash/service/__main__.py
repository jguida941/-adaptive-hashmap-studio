"""Command-line entry point for the control surface service."""

from __future__ import annotations

import argparse
import importlib
import logging
from typing import Optional

from .api import create_app
from .jobs import JobManager

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9600


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Adaptive Hash Map control surface service.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Interface to bind (default: %(default)s).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: %(default)s).")
    parser.add_argument(
        "--job-root",
        type=str,
        default=None,
        help="Directory for job metadata/logs (defaults to ADHASH_JOB_ROOT or runs/jobs).",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum concurrent jobs (defaults to ADHASH_MAX_JOBS or 4).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload (development only; requires watchgod).",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        help="Uvicorn log level (default: %(default)s).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    manager = JobManager(base_dir=args.job_root, max_workers=args.max_jobs)
    app = create_app(manager)

    log_level = args.log_level.lower()
    logging.getLogger("adhash.service").setLevel(log_level.upper())

    uvicorn = importlib.import_module("uvicorn")
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=log_level,
        reload=args.reload,
    )


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    main()
