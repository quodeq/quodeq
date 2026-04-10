"""Frozen-app subprocess command helpers for PyInstaller bundles."""
from __future__ import annotations

import os
import subprocess
import sys

_MODULE_MAP = {
    "api": "quodeq.api.app",
    "webview": "quodeq.dashboard._webview_window",
}

_CMD_DISCOVERY_TIMEOUT_S = 5


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


def source_user_path() -> None:
    """Load the user's shell PATH since .app bundles don't inherit it.

    Only needed on macOS/Linux when running inside a frozen bundle.
    """
    if not is_frozen() or sys.platform == "win32":
        return
    try:
        cmd = ('source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; '
               'source ~/.bash_profile 2>/dev/null; echo $PATH')
        shell = os.environ.get("SHELL", "/bin/zsh")
        result = subprocess.run(
            [shell, "-c", cmd], capture_output=True, text=True,
            timeout=_CMD_DISCOVERY_TIMEOUT_S,
        )
        if result.returncode == 0 and result.stdout.strip():
            os.environ["PATH"] = result.stdout.strip()
            return
    except (subprocess.TimeoutExpired, OSError):
        pass
    # Fallback: add common locations
    import platform
    brew = "/opt/homebrew/bin" if platform.machine() == "arm64" else "/usr/local/bin"
    extra = f"{os.path.expanduser('~/.local/bin')}:{brew}"
    os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{extra}"
