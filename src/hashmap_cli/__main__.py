"""Module entry-point shim for `python -m hashmap_cli`."""

from __future__ import annotations

from adhash.hashmap_cli import console_main


def main() -> None:  # pragma: no cover - thin wrapper
    console_main()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
