"""Node/npm prerequisite checks (provider checks live in analysis/prereqs.py)."""
from __future__ import annotations

import re
import subprocess

from quodeq.shared.utils import IS_WIN32 as _IS_WIN32

_INSTALL_HINT_NODE = (
    "Install Node.js + npm from https://nodejs.org/ or via your package manager:\n"
    "  brew install node                    # macOS (installs both)\n"
    "  sudo apt install -y nodejs npm       # Ubuntu/Debian (two packages)\n"
    "  sudo dnf install -y nodejs npm       # Fedora/RHEL\n"
    "  pacman -S nodejs npm                 # Arch"
)

_VERSION_CMD_TIMEOUT_S = 30

# Provider/command tokens are restricted to a charset with no shell
# metacharacters, so even on the Windows shell=True path (needed for npm
# .cmd shim resolution) a value like "x & calc.exe" can never reach cmd.exe.
_SAFE_CMD_TOKEN_RE = re.compile(r"[A-Za-z0-9._-]+")


def _run_version_cmd(cmd: list[str]) -> str:
    """Run a version command and return its stdout, or raise.

    On Windows ``shell=True`` is required so npm-installed ``.cmd`` shims
    resolve on PATH. To keep that shell safe, every token in *cmd* is
    validated against a strict ``[A-Za-z0-9._-]`` charset, so no shell
    metacharacter (space, ``&``, ``|``, ``>`` ...) can reach ``cmd.exe``.
    Callers that accept external input (e.g. a provider name from the
    ``AI_CMD`` env var) must still validate at their own layer; this is
    defense in depth.
    """
    if not isinstance(cmd, list):
        raise TypeError("cmd must be a list of strings, not a raw string")
    for token in cmd:
        if not isinstance(token, str) or not _SAFE_CMD_TOKEN_RE.fullmatch(token):
            raise ValueError(f"unsafe command token: {token!r}")
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", check=True, shell=_IS_WIN32,
        timeout=_VERSION_CMD_TIMEOUT_S,
    )
    return result.stdout.strip()


def _parse_major(version_str: str) -> int:
    """Extract the major version number from a version string like 'v20.11.0' or '10.2.0'."""
    cleaned = version_str.lstrip("v")
    return int(cleaned.split(".")[0])


def _check_tool_version(cmd: list[str], tool_name: str, min_major: int, install_hint: str) -> None:
    """Raise RuntimeError if *tool_name* is missing or below *min_major*."""
    try:
        version_str = _run_version_cmd(cmd)
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"{tool_name} {min_major}+ is required but not found.\n{install_hint}"
        ) from exc
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return
    if major < min_major:
        raise RuntimeError(
            f"{tool_name} {version_str} is below the minimum required version {min_major}.x.\n"
            f"{install_hint}"
        )


def check_node(min_major: int = 20) -> None:
    """Raise RuntimeError if Node.js is missing or below minimum version."""
    _check_tool_version(["node", "--version"], "Node.js", min_major, _INSTALL_HINT_NODE)


def check_npm(min_major: int = 10) -> None:
    """Raise RuntimeError if npm is missing or below minimum version."""
    _check_tool_version(["npm", "--version"], "npm", min_major, _INSTALL_HINT_NODE)


def _collect_tool_issue(cmd: list[str], tool_name: str, min_major: int) -> str | None:
    """Return a one-line description of a tool problem, or None if OK.

    Used by aggregators that want to report every missing/outdated tool in
    a single error instead of failing fast on the first one.
    """
    try:
        version_str = _run_version_cmd(cmd)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return f"{tool_name} {min_major}+ not found on PATH"
    try:
        major = _parse_major(version_str)
    except (ValueError, IndexError):
        return None
    if major < min_major:
        return f"{tool_name} {version_str} is below the minimum required version {min_major}.x"
    return None


def check_dashboard_dev_prereqs() -> None:
    """Check Node.js and npm prerequisites for `quodeq dashboard --dev`.

    Production dashboards ship a pre-built UI inside the wheel and do not
    require Node or npm at runtime. This check is only relevant when
    running with `--dev`, which rebuilds the UI from source on the user's
    machine.

    Runs every tool check, collects any issues, and raises a single
    RuntimeError listing them all, so a contributor missing both Node and
    npm (common on fresh Debian/Ubuntu systems where they ship as separate
    packages) gets the full story in one message with one install command.
    """
    issues: list[str] = []
    node_issue = _collect_tool_issue(["node", "--version"], "Node.js", 20)
    if node_issue is not None:
        issues.append(node_issue)
    npm_issue = _collect_tool_issue(["npm", "--version"], "npm", 10)
    if npm_issue is not None:
        issues.append(npm_issue)
    if not issues:
        return
    bullets = "\n".join(f"  - {issue}" for issue in issues)
    raise RuntimeError(
        f"Missing or outdated prerequisites:\n{bullets}\n\n{_INSTALL_HINT_NODE}"
    )
