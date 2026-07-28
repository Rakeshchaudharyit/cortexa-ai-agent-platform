#!/usr/bin/env python3
"""Fail if the frontend HTML references Next static assets that do not load."""

from __future__ import annotations

import re
import sys
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ASSET_PATTERN = re.compile(r'(/_next/static/[^"\')\s>]+)')


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "cortexa-asset-check/1.0"})
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", "replace")


def fetch_status(url: str) -> int:
    request = Request(url, headers={"User-Agent": "cortexa-asset-check/1.0"})
    with urlopen(request, timeout=15) as response:
        return int(response.status)


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:3000"
    html = fetch_text(base_url)
    assets = []
    for match in ASSET_PATTERN.finditer(html):
        asset = unescape(match.group(1)).rstrip("\\")
        if asset not in assets:
            assets.append(asset)

    if not assets:
        print(f"FAIL: no /_next/static assets found in {base_url}")
        return 1

    checked = 0
    for asset in assets[:5]:
        asset_url = urljoin(base_url, asset)
        try:
            status = fetch_status(asset_url)
        except HTTPError as exc:
            print(f"FAIL: {asset_url} returned HTTP {exc.code}")
            return 1
        except URLError as exc:
            print(f"FAIL: {asset_url} could not be fetched: {exc.reason}")
            return 1

        print(f"PASS: {asset_url} -> HTTP {status}")
        if status != 200:
            print(f"FAIL: expected HTTP 200 for {asset_url}")
            return 1
        checked += 1

    print(f"PASS: validated {checked} referenced Next static asset(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
