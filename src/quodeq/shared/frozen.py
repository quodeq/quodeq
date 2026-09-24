"""Frozen-app subprocess command helpers for PyInstaller bundles.

Lives in shared/ (stdlib-only, cross-cutting) so delivery layers that must
not import each other (dashboard, menubar) can share one launch vocabulary.
dashboard/_frozen.py re-exports these names for its existing importers."""
from __future__ import annotations

import logging
import platform
import subprocess
import sys
from collections.abc import MutableMapping
from os.path import expanduser

from quodeq.shared.constants import PLATFORM_WIN32
from quodeq.shared.env_resolve import resolve_env_mut

_logger = logging.getLogger(__name__)

_MACHINE_ARM64 = "arm64"  # platform.machine() value

_MODULE_MAP = {
    "api": "quodeq.api.app",
    "webview": "quodeq.dashboard._webview_window",
    "evaluate": "quodeq.cli",
    "menubar": "quodeq.menubar",
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


def dashboard_cmd(args: list[str] | None = None) -> list[str]:
    """Return the command that launches the full dashboard (not a --_ mode).

    Frozen:   [sys.executable, ...args]   (entry falls through to the dashboard CLI)
    Unfrozen: [sys.executable, "-m", "quodeq.dashboard", ...args]
    """
    extra = args or []
    if is_frozen():
        return [sys.executable] + extra
    return [sys.executable, "-m", "quodeq.dashboard"] + extra


def source_user_path(env: MutableMapping[str, str] | None = None) -> None:
    """Load the user's shell PATH since .app bundles don't inherit it.

    Only needed on macOS/Linux when running inside a frozen bundle.

    *env* is the mapping ``SHELL`` is read from and ``PATH`` is written
    back into; ``None`` means this process's own environment.
    """
    if not is_frozen() or sys.platform == PLATFORM_WIN32:
        return
    environ = resolve_env_mut(env)
    try:
        # macOS-standard shell profile paths. These cover the default zsh
        # and bash configurations; exotic setups may need QUODEQ_PATH override.
        cmd = ('source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; '
               'source ~/.bash_profile 2>/dev/null; echo $PATH')
        shell = environ.get("SHELL", "/bin/zsh")
        if shell not in _ALLOWED_SHELLS:
            shell = "/bin/zsh"
        result = subprocess.run(
            [shell, "-c", cmd], capture_output=True, text=True, encoding="utf-8",
            timeout=_CMD_DISCOVERY_TIMEOUT_S,
        )
        if result.returncode == 0 and result.stdout.strip():
            environ["PATH"] = result.stdout.strip()
            return
    except (subprocess.TimeoutExpired, OSError) as exc:
        _logger.debug("login-shell PATH discovery failed, using fallback locations: %s", exc)
    # Fallback: add common locations
    brew = "/opt/homebrew/bin" if platform.machine() == _MACHINE_ARM64 else "/usr/local/bin"
    extra = f"{expanduser('~/.local/bin')}:{brew}"
    environ["PATH"] = f"{environ.get('PATH', '')}:{extra}"
