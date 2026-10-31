"""Manual update check (Phase 4).

The dashboard asks GitHub Releases for the latest stable release and
tells the user a newer version exists, with a download link. It never
downloads or installs anything: auto-update is a later phase, once
signing exists, because an unsigned auto-updater is worse than a
manual one (see the plan, section 7).

The check only ever offers stable releases: GitHub's /releases/latest
endpoint excludes prereleases and drafts, so beta builds are never
offered here. Beta opt-in is separate Phase 4 work.

Network failure, an unexpected response, or a malformed version is a
plain-language error, never an exception in the dashboard.
"""
from __future__ import annotations

import json
import urllib.request

# Keep in sync with the build scripts' SIDEE_BUILD_VERSION default
# (packaging/*.spec, tools/build_*_release.py) and Android versionName.
# Phase 5 adds a CI test for this mapping; until then, bump them together.
CURRENT_VERSION = "0.2.0.1"
LATEST_RELEASE_URL = (
    "https://api.github.com/repos/JohnCarter2021/Sidee/releases/latest"
)
RELEASES_URL = "https://github.com/JohnCarter2021/Sidee/releases"
TIMEOUT_SECONDS = 5


def parse_version(value: str) -> tuple[int, ...] | None:
    """Parse "v0.1.4.2" / "0.1.4.2" into (0, 1, 4, 2); None if malformed."""
    text = str(value or "").strip()
    if text.startswith("v"):
        text = text[1:]
    if not text:
        return None
    parts = []
    for piece in text.split("."):
        if not piece.isdigit():
            return None
        parts.append(int(piece))
    return tuple(parts)


def _fetch_latest() -> dict:
    request = urllib.request.Request(
        LATEST_RELEASE_URL, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def check(fetch=None) -> dict:
    """Return the update state; `fetch` is injected by tests."""
    fetch = fetch or _fetch_latest
    try:
        data = fetch()
    except Exception:
        return {
            "ok": False,
            "current": CURRENT_VERSION,
            "error": "Couldn't reach the release page. "
            "Check your connection and try again.",
        }
    if not isinstance(data, dict):
        return {
            "ok": False,
            "current": CURRENT_VERSION,
            "error": "The release page gave an unexpected answer. Try again later.",
        }
    latest = parse_version(data.get("tag_name", ""))
    if latest is None:
        return {
            "ok": False,
            "current": CURRENT_VERSION,
            "error": "The release page gave an unexpected version. Try again later.",
        }
    current = parse_version(CURRENT_VERSION)
    return {
        "ok": True,
        "current": CURRENT_VERSION,
        "latest": ".".join(str(n) for n in latest),
        "update_available": latest > current,
        "url": data.get("html_url") or RELEASES_URL,
    }
