"""Helper functions for the macOS menu bar app — command discovery and health checks."""
from __future__ import annotations

import functools
import json
import os
import subprocess
import urllib.error
import urllib.request

_HEALTH_TIMEOUT = 1.0
_CMD_DISCOVERY_TIMEOUT_S = 5
_HOMEBREW_ARM64 = "/opt/homebrew/bin"
_HOMEBREW_X86 = "/usr/local/bin"


def _homebrew_bin_dirs(
    arm64_path: str = _HOMEBREW_ARM64,
    x86_path: str = _HOMEBREW_X86,
) -> str:
    """Return Homebrew bin directories based on the CPU architecture.

    *arm64_path* and *x86_path* can be overridden for testing or
    non-standard Homebrew installations.
    """
    import platform
    arch = platform.machine()
    if arch == "arm64":
        return arm64_path
    elif arch == "x86_64":
        return x86_path
    return f"{arm64_path}:{x86_path}"

def source_user_path() -> None:
    """Load the user's shell PATH since .app bundles don't inherit it."""
    try:
        cmd = ('source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; '
               'source ~/.bash_profile 2>/dev/null; echo $PATH')
        shell = os.environ.get("SHELL", "/bin/zsh")
        result = subprocess.run([shell, "-c", cmd], capture_output=True, text=True, timeout=_CMD_DISCOVERY_TIMEOUT_S)
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


def find_commands(env: dict[str, str] | None = None) -> dict[str, str | None]:
    """Check which required commands are available.

    An optional *env* mapping can be passed to override the subprocess
    environment (useful for testing).  When *env* is ``None`` the result
    is cached; when a custom *env* is supplied the cache is bypassed so
    callers can test with different PATH values.
    """
    if env is None:
        return _find_commands_cached()
    return _find_commands_uncached(env)


@functools.lru_cache(maxsize=1)
def _find_commands_cached() -> dict[str, str | None]:
    return _find_commands_uncached(env=None)


def clear_commands_cache() -> None:
    """Clear the find_commands LRU cache. Useful for test isolation."""
    _find_commands_cached.cache_clear()


def _find_commands_uncached(env: dict[str, str] | None) -> dict[str, str | None]:
    cmds: dict[str, str | None] = {}
    for name in ("python3", "node", "claude", "quodeq"):
        try:
            result = subprocess.run(
                ["which", name], capture_output=True, text=True, timeout=_CMD_DISCOVERY_TIMEOUT_S,
                env=env,
            )
            cmds[name] = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            cmds[name] = None
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
