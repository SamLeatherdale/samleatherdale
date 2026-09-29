#!/usr/bin/env python3
"""Save a static GitHub profile trophy into this repo.

The profile used to hotlink a live github-profile-trophy server. Those
volunteer deployments go offline often, and the image breaks when they do.
This script reads the load-balancing endpoint list from the upstream README,
requests the trophy with the style configured below, and writes the first
response that is actually an image.

Refresh the committed image with:

    python3 scripts/fetch-github-trophy.py
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UPSTREAM_README = (
    "https://raw.githubusercontent.com/ryo-ma/github-profile-trophy/master/README.md"
)
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "images" / "github-profile-trophy.svg"

# Style currently shown on the profile (monokai, one row of six).
QUERY = {
    "username": "samleatherdale",
    "theme": "monokai",
    "column": "6",
    "row": "1",
}

USER_AGENT = "samleatherdale-trophy-snapshot/1.0"
TIMEOUT_SECONDS = 30
MIN_IMAGE_BYTES = 2000


def fetch(url: str) -> tuple[int, str, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "image/svg+xml,image/png,image/*;q=0.8,*/*;q=0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        body = error.read()
        content_type = error.headers.get("Content-Type", "") if error.headers else ""
        return error.code, content_type, body


def load_balancing_endpoints(readme: str) -> list[str]:
    """Return volunteer trophy base URLs, in the order the upstream README lists them."""
    match = re.search(
        r"^# Load balancing endpoints\s*(.*?)^# ",
        readme,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            "Could not find a '# Load balancing endpoints' section in the upstream README"
        )

    endpoints: list[str] = []
    seen: set[str] = set()
    for raw in re.findall(r"https?://[^\s)>\]]+", match.group(1)):
        if "github.com/" in raw:
            continue
        base = raw.rstrip("/")
        if base in seen:
            continue
        seen.add(base)
        endpoints.append(base)
    return endpoints


def is_trophy_image(status: int, content_type: str, body: bytes) -> bool:
    if status != 200 or len(body) < MIN_IMAGE_BYTES:
        return False

    sample = body.lstrip()[:800].lower()
    head = body[:1500].lower()
    if (
        sample.startswith((b"<!doctype", b"<html"))
        or b"deployment_not_found" in head
        or b"function_invocation_failed" in head
        or b"just a moment" in head
    ):
        return False

    content_type = content_type.lower()
    if "html" in content_type:
        return False

    is_svg = "svg" in content_type or sample.startswith((b"<svg", b"<?xml"))
    if is_svg:
        lowered = body.lower()
        return (
            b"<svg" in lowered
            and b"</svg>" in lowered
            and b"viewbox" in lowered
            and b"<text" in lowered
        )

    if content_type.startswith("text/"):
        return False
    if sample.startswith(b"\x89png") or "png" in content_type:
        return True
    if sample.startswith(b"\xff\xd8") or "jpeg" in content_type or "jpg" in content_type:
        return True
    return False


def main() -> int:
    print(f"Reading load-balancing endpoints from {UPSTREAM_README}")
    try:
        status, _content_type, body = fetch(UPSTREAM_README)
    except Exception as error:  # noqa: BLE001 - report any network failure and stop
        print(f"Failed to download the upstream README: {error}", file=sys.stderr)
        return 1
    if status != 200:
        print(f"Upstream README request failed with HTTP {status}", file=sys.stderr)
        return 1

    try:
        endpoints = load_balancing_endpoints(body.decode("utf-8"))
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    if not endpoints:
        print("The upstream README listed no load-balancing endpoints", file=sys.stderr)
        return 1

    print(f"Found {len(endpoints)} endpoints")
    query = urllib.parse.urlencode(QUERY)
    for base in endpoints:
        url = f"{base}/?{query}"
        print(f"Trying {url}")
        try:
            status, content_type, image = fetch(url)
        except Exception as error:  # noqa: BLE001 - try the next volunteer endpoint
            print(f"  request failed: {error}")
            continue
        if is_trophy_image(status, content_type, image):
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_bytes(image)
            print(f"Saved {OUTPUT.relative_to(REPO_ROOT)} ({len(image)} bytes) from {base}")
            return 0
        print(
            f"  skipped (HTTP {status}, {content_type or 'unknown content type'}, {len(image)} bytes)"
        )

    print("No load-balancing endpoint returned a valid trophy image", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
