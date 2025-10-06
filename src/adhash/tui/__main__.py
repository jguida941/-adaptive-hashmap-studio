"""CLI entry point for the Adaptive Hash Map Textual TUI."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from .app import run_tui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Interactive terminal dashboard for Adaptive Hash Map metrics.",
    )
    parser.add_argument(
        "--metrics-endpoint",
        default="http://127.0.0.1:9090/api/metrics",
        help="HTTP endpoint exposing the latest metrics JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--history-endpoint",
        default=None,
        help="Optional history endpoint for future visualisations.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between refreshes (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="HTTP timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--probe-json",
        default=None,
        help="Optional probe trace JSON to display inside the TUI.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    run_tui(
        metrics_endpoint=args.metrics_endpoint,
        history_endpoint=args.history_endpoint,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
        probe_trace=args.probe_json,
    )


if __name__ == "__main__":
    main()
