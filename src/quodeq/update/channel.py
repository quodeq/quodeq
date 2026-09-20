"""Detect how quodeq was installed and the matching upgrade command.

Path-based and dependency-free. An ambiguous result MUST fall back to the
generic pip command rather than guess wrong (telling a pipx user to run
`pip install -U` breaks their isolated venv).
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from quodeq.shared._env_resolve import resolve_env

_PACKAGE = "quodeq"
_FALLBACK = f"pip install -U {_PACKAGE}"


def detect_channel() -> str:
    """Return "frozen" for the bundled app, "wheel" for a pip-style install."""
    return "frozen" if getattr(sys, "frozen", False) else "wheel"


def upgrade_command(
    env: Mapping[str, str] | None = None,
    package_file: str | None = None,
) -> str:
    """Return the shell command that upgrades this install, "" when frozen.

    Decided by where the package file sits: a pipx, uv-tool, or Homebrew root
    in the path picks that tool's command. Anything unrecognised falls back to
    ``pip install -U``. *env* and *package_file* exist for tests.
    """
    if detect_channel() == "frozen":
        return ""
    environ = resolve_env(env)
    try:
        path = str(Path(package_file or __file__).resolve()).replace("\\", "/")
    except OSError:
        return _FALLBACK

    pipx_home = environ.get("PIPX_HOME")
    uv_tool_dir = environ.get("UV_TOOL_DIR")
    roots = [
        (pipx_home, f"pipx upgrade {_PACKAGE}"),
        (str(Path.home() / ".local" / "pipx" / "venvs"), f"pipx upgrade {_PACKAGE}"),
        ("/pipx/venvs", f"pipx upgrade {_PACKAGE}"),
        (uv_tool_dir, f"uv tool upgrade {_PACKAGE}"),
        (str(Path.home() / ".local" / "share" / "uv" / "tools"), f"uv tool upgrade {_PACKAGE}"),
        ("/uv/tools", f"uv tool upgrade {_PACKAGE}"),
        ("/Cellar/", f"brew upgrade {_PACKAGE}"),
        ("/homebrew/", f"brew upgrade {_PACKAGE}"),
    ]
    for root, command in roots:
        if root and root.replace("\\", "/") in path:
            return command
    return _FALLBACK
