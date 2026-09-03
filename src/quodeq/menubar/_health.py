"""Menu bar helpers — icon lookup, command discovery, and dashboard health checks.

Ported from packaging/macos/_helpers.py when the menu bar became a built-in
feature. PATH sourcing lives in quodeq.dashboard._frozen.source_user_path.
"""
from __future__ import annotations

import functools
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_HEALTH_TIMEOUT = 1.0
_CMD_DISCOVERY_TIMEOUT_S = 5
_API_HEALTH_PATH = "/api/health"
_API_EVALUATIONS_PATH = "/api/evaluations"
_LOCAL_BASE_URL = "http://127.0.0.1"
_DEFAULT_COMMANDS = ("python3", "node", "claude")


def _icons_dir() -> Path:
    """Directory holding the menu bar PNGs, in dev and frozen modes."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "quodeq" / "data" / "icons" / "menubar"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "data" / "icons" / "menubar"


def find_icon(name: str) -> str | None:
    """Find a menu bar icon by filename."""
    path = _icons_dir() / name
    return str(path) if path.exists() else None


def find_commands(
    names: tuple[str, ...] = _DEFAULT_COMMANDS, env: dict[str, str] | None = None,
) -> dict[str, str | None]:
    """Check which required commands are available.

    When *env* is ``None`` the result is cached; a custom *env* bypasses the
    cache so callers can test with different PATH values.
    """
    if env is None:
        return _find_commands_cached(names)
    return _find_commands_uncached(names, env)


@functools.lru_cache(maxsize=4)
def _find_commands_cached(names: tuple[str, ...]) -> dict[str, str | None]:
    return _find_commands_uncached(names, env=None)


def clear_commands_cache() -> None:
    """Clear the find_commands LRU cache. Useful for test isolation."""
    _find_commands_cached.cache_clear()


def _find_commands_uncached(
    names: tuple[str, ...], env: dict[str, str] | None,
) -> dict[str, str | None]:
    cmds: dict[str, str | None] = {}
    for name in names:
        try:
            result = subprocess.run(
                ["which", name], capture_output=True, text=True, encoding="utf-8",
                timeout=_CMD_DISCOVERY_TIMEOUT_S, env=env,
            )
            cmds[name] = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            cmds[name] = None
    return cmds


def health_check(port: int) -> bool:
    """Check if the dashboard is responding on the given port."""
    try:
        url = f"{_LOCAL_BASE_URL}:{port}{_API_HEALTH_PATH}"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return json.loads(r.read()).get("ok") is True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


def is_evaluating(port: int) -> bool:
    """Check if any evaluation job is currently running."""
    try:
        url = f"{_LOCAL_BASE_URL}:{port}{_API_EVALUATIONS_PATH}?limit=1&status=running"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return any(j.get("status") == "running" for j in json.loads(r.read()))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False
