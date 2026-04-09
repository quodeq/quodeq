"""Frozen-app subprocess command helpers for PyInstaller bundles."""
from __future__ import annotations

import sys

_MODULE_MAP = {
    "api": "quodeq.api.app",
    "webview": "quodeq.dashboard._webview_window",
}


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def subprocess_cmd(mode: str, args: list[str] | None = None) -> list[str]:
    """Return the subprocess command for *mode*.

    Frozen:   [sys.executable, "--_<mode>", ...args]
    Unfrozen: [sys.executable, "-m", "<module>", ...args]
    """
    extra = args or []
    if is_frozen():
        return [sys.executable, f"--_{mode}"] + extra
    return [sys.executable, "-m", _MODULE_MAP[mode]] + extra
