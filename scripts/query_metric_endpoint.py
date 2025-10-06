"""Fetch a metrics endpoint and print its JSON payload (curl replacement)."""

from __future__ import annotations

import argparse
import json
from typing import Any

from urllib.error import URLError
from urllib.request import Request, urlopen


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=2.0) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Query a metrics endpoint and dump JSON.")
    parser.add_argument("url", help="URL to fetch (e.g. http://127.0.0.1:9090/api/metrics)")
    parser.add_argument("jq_path", nargs="?", default=None, help="Optional dotted path to extract from the JSON")
    args = parser.parse_args()

    try:
        data = fetch_json(args.url)
    except URLError as exc:  # noqa: BLE001
        print(f"Request failed: {exc}")
        return 1

    if args.jq_path:
        current: Any = data
        for key in args.jq_path.split('.'):
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
