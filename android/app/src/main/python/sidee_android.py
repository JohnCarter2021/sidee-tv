"""Android entry point for the Sidee dashboard (Phase 3 spike).

The shared core is copied into src/main/python/core at build time
(see app/build.gradle.kts copyCore); this module is the only Android
-specific Python file. It starts the same dashboard server the
desktop launchers use, bound to loopback only, with state in the
app's private files directory passed in from Kotlin.
"""
from __future__ import annotations

import os

_dashboard = None


def start(state_dir: str) -> str:
    """Start the dashboard on loopback and return its keyed URL."""
    global _dashboard
    if _dashboard is not None:
        return _dashboard.url
    os.environ["SIDEE_STATE_DIR"] = state_dir
    from core import webui

    _dashboard = webui.Dashboard(port=0, headless=True, host="127.0.0.1")
    _dashboard.start()
    return _dashboard.url


def stop() -> None:
    """Stop the dashboard, if running."""
    global _dashboard
    if _dashboard is not None:
        _dashboard.close()
        _dashboard = None
