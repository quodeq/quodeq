"""Frozen-app subprocess command helpers for PyInstaller bundles."""
from __future__ import annotations

import os
import platform
import subprocess
import sys

_MODULE_MAP = {
    "api": "quodeq.api.app",
    "webview": "quodeq.dashboard._webview_window",
    "evaluate": "quodeq.cli",
}

_CMD_DISCOVERY_TIMEOUT_S = 5

# SECURITY: Only allow well-known shell paths to prevent execution of
# arbitrary binaries via a crafted $SHELL environment variable.
_ALLOWED_SHELLS = {
    "/bin/bash", "/bin/zsh", "/bin/sh",
    "/usr/bin/bash", "/usr/bin/zsh", "/usr/bin/sh",
    "/usr/local/bin/bash", "/usr/local/bin/zsh",
    "/opt/homebrew/bin/bash", "/opt/homebrew/bin/zsh",
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


def source_user_path() -> None:
    """Load the user's shell PATH since .app bundles don't inherit it.

    Only needed on macOS/Linux when running inside a frozen bundle.
    """
    if not is_frozen() or sys.platform == "win32":
        return
    try:
        # macOS-standard shell profile paths. These cover the default zsh
        # and bash configurations; exotic setups may need QUODEQ_PATH override.
        cmd = ('source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; '
               'source ~/.bash_profile 2>/dev/null; echo $PATH')
        shell = os.environ.get("SHELL", "/bin/zsh")
        if shell not in _ALLOWED_SHELLS:
            shell = "/bin/zsh"
        result = subprocess.run(
            [shell, "-c", cmd], capture_output=True, text=True, encoding="utf-8",
            timeout=_CMD_DISCOVERY_TIMEOUT_S,
        )
        if result.returncode == 0 and result.stdout.strip():
            os.environ["PATH"] = result.stdout.strip()
            return
    except (subprocess.TimeoutExpired, OSError):
        pass
    # Fallback: add common locations
    brew = "/opt/homebrew/bin" if platform.machine() == "arm64" else "/usr/local/bin"
    extra = f"{os.path.expanduser('~/.local/bin')}:{brew}"
    os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{extra}"
