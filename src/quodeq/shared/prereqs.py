"""Prerequisite checks for external tool dependencies."""
from __future__ import annotations

import subprocess

from quodeq.shared.utils import IS_WIN32 as _IS_WIN32

_INSTALL_HINT_NODE = (
    "Install it from https://nodejs.org/ or via your package manager:\n"
    "  brew install node        # macOS\n"
    "  apt install nodejs       # Ubuntu/Debian"
)

_INSTALL_HINT_CLAUDE = (
    "Install it from https://docs.anthropic.com/en/docs/claude-code/overview\n"
    "  npm install -g @anthropic-ai/claude-code"
)


def _run_version_cmd(cmd: list[str]) -> str:
    """Run a command and return its stdout, or raise FileNotFoundError."""
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, shell=_IS_WIN32,
    )
    return result.stdout.strip()


def _parse_major(version_str: str) -> int:
    """Extract the major version number from a version string like 'v20.11.0' or '10.2.0'."""
    cleaned = version_str.lstrip("v")
    return int(cleaned.split(".")[0])


def check_node(min_major: int = 18) -> None:
    """Raise RuntimeError if Node.js is missing or below minimum version."""
    try:
        version_str = _run_version_cmd(["node", "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"Node.js {min_major}+ is required but not found.\n{_INSTALL_HINT_NODE}"
        ) from exc
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return
    if major < min_major:
        raise RuntimeError(
            f"Node.js {version_str} is below the minimum required version {min_major}.x.\n"
            f"{_INSTALL_HINT_NODE}"
        )


def check_npm(min_major: int = 9) -> None:
    """Raise RuntimeError if npm is missing or below minimum version."""
    try:
        version_str = _run_version_cmd(["npm", "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"npm {min_major}+ is required but not found.\n{_INSTALL_HINT_NODE}"
        ) from exc
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return
    if major < min_major:
        raise RuntimeError(
            f"npm {version_str} is below the minimum required version {min_major}.x.\n"
            f"{_INSTALL_HINT_NODE}"
        )


def check_claude_code() -> None:
    """Raise RuntimeError if Claude Code CLI is not available."""
    try:
        _run_version_cmd(["claude", "--version"])
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"Claude Code is required but not found.\n{_INSTALL_HINT_CLAUDE}"
        ) from exc


def check_dashboard_prereqs() -> None:
    """Check all prerequisites for the dashboard command."""
    check_node()
    check_npm()


def check_evaluate_prereqs() -> None:
    """Check all prerequisites for the evaluate command."""
    check_claude_code()
