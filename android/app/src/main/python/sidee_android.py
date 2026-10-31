"""Android entry point for the Sidee dashboard (Phase 3 spike).

The shared core is copied into src/main/python/core at build time
(see app/build.gradle.kts copyCore); this module is the only Android
-specific Python file. It starts the same dashboard server the
desktop launchers use, bound to all interfaces so LAN devices (a TV
browser opening /tv/) can reach it, with state in the app's private
files directory passed in from Kotlin. The in-app WebView still loads
the loopback URL; the TV uses the phone's LAN address instead.
"""
from __future__ import annotations

import os

_dashboard = None


def start(state_dir: str) -> str:
    """Start the dashboard on all interfaces and return the loopback
    URL for the in-app WebView. LAN devices reach the same server at
    the phone's Wi-Fi address (see the dashboard's phone section).

    No port is pinned here on purpose: the dashboard prefers its saved
    port (then 8787), so the Sidee TV tile's address stays stable across
    app launches instead of changing with every random port.
    """
    global _dashboard
    if _dashboard is not None:
        return _dashboard.url
    os.environ["SIDEE_STATE_DIR"] = state_dir
    from core import webui

    _dashboard = webui.Dashboard(headless=True, host="0.0.0.0")
    _dashboard.start()
    return _dashboard.url


def stop() -> None:
    """Stop the dashboard, if running."""
    global _dashboard
    if _dashboard is not None:
        _dashboard.close()
        _dashboard = None
