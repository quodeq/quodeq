"""Detect how quodeq was installed and the matching upgrade command.

Path-based and dependency-free. An ambiguous result MUST fall back to the
generic pip command rather than guess wrong (telling a pipx user to run
`pip install -U` breaks their isolated venv).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PACKAGE = "quodeq"
_FALLBACK = f"pip install -U {_PACKAGE}"


def detect_channel() -> str:
    return "frozen" if getattr(sys, "frozen", False) else "wheel"


def upgrade_command(
    env: dict[str, str] | None = None,
    package_file: str | None = None,
) -> str:
    if detect_channel() == "frozen":
        return ""
    environ = env if env is not None else os.environ
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
