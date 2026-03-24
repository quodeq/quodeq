"""Helper functions for the macOS menu bar app — command discovery and health checks."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request

_HEALTH_TIMEOUT = 1.0
_HOMEBREW_ARM64 = "/opt/homebrew/bin"
_HOMEBREW_X86 = "/usr/local/bin"


def _homebrew_bin_dirs() -> str:
    """Return Homebrew bin directories based on the CPU architecture."""
    import platform
    arch = platform.machine()
    if arch == "arm64":
        return _HOMEBREW_ARM64
    elif arch == "x86_64":
        return _HOMEBREW_X86
    return f"{_HOMEBREW_ARM64}:{_HOMEBREW_X86}"

_cached_commands: dict[str, str | None] | None = None


def source_user_path() -> None:
    """Load the user's shell PATH since .app bundles don't inherit it."""
    try:
        cmd = ('source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; '
               'source ~/.bash_profile 2>/dev/null; echo $PATH')
        shell = os.environ.get("SHELL", "/bin/zsh")
        result = subprocess.run([shell, "-c", cmd], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            os.environ["PATH"] = result.stdout.strip()
            return
    except (subprocess.TimeoutExpired, OSError):
        pass
    extra = f"{os.path.expanduser('~/.local/bin')}:{_homebrew_bin_dirs()}"
    os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{extra}"


def find_icon(name: str) -> str | None:
    """Find a menu bar icon by filename."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in [here, os.path.join(os.path.dirname(here), "Resources")]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return None


def find_commands() -> dict[str, str | None]:
    """Check which required commands are available (cached after first call)."""
    global _cached_commands
    if _cached_commands is not None:
        return _cached_commands
    cmds = {}
    for name in ("python3", "node", "claude", "quodeq"):
        try:
            result = subprocess.run(
                ["which", name], capture_output=True, text=True, timeout=5,
            )
            cmds[name] = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            cmds[name] = None
    _cached_commands = cmds
    return cmds


def health_check(port: int) -> bool:
    """Check if the dashboard is responding on the given port."""
    try:
        url = f"http://127.0.0.1:{port}/api/health"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return json.loads(r.read()).get("ok") is True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


def is_evaluating(port: int) -> bool:
    """Check if any evaluation job is currently running."""
    try:
        url = f"http://127.0.0.1:{port}/api/evaluations"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return any(j.get("status") == "running" for j in json.loads(r.read()))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False
