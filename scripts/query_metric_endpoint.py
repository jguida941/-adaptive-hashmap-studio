"""Fetch a metrics endpoint and print its JSON payload (curl replacement)."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ALLOWED_SCHEMES = {"http", "https"}


def _validated_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme '{parsed.scheme}' (allowed: http, https)")
    if not parsed.hostname:
        raise ValueError("URL must include a host")
    return url


def fetch_json(url: str) -> dict[str, Any]:
    safe_url = _validated_url(url)
    request = Request(safe_url, headers={"Accept": "application/json"})  # noqa: S310  # nosec B310
    # URL scheme and host are validated in _validated_url.
    with urlopen(request, timeout=2.0) as response:  # noqa: S310  # nosec B310
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Query a metrics endpoint and dump JSON.")
    parser.add_argument("url", help="URL to fetch (e.g. http://127.0.0.1:9090/api/metrics)")
    parser.add_argument(
        "jq_path", nargs="?", default=None, help="Optional dotted path to extract from the JSON"
    )
    args = parser.parse_args()

    try:
        data = fetch_json(args.url)
    except HTTPError as exc:
        print(f"HTTP error: {exc}")
        return 1
    except (URLError, ValueError, OSError) as exc:
        print(f"Request failed: {exc}")
        return 1

    if args.jq_path:
        current: Any = data
        for key in args.jq_path.split("."):
            if isinstance(current, dict):
                current = current.get(key)
            else:
                current = None
                break
        print(json.dumps(current, indent=2))
    else:
        print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
