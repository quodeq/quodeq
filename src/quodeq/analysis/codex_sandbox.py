"""Codex's own sandbox for scans, where it works with the findings MCP tools.

From Codex 0.162, ``-s read-only`` with ``approval_policy = "never"`` keeps
MCP tool calls working once the findings server's tools are pre-approved
(``default_tools_approval_mode``). Shell commands then run with no network
at all (Quodeq's API on loopback included), no writes, and a permission
profile that makes the user's home unreadable except the analysed repo and
this project's evaluations (the standards checklist sits in its evidence).

Codex enforces this on macOS, Linux and Windows, so it covers machines where
Quodeq has no OS sandbox of its own. A probe runs one read under the same
profile first; where it fails (an older Codex, a Linux kernel or container
that refuses the sandbox, an unconfigured Windows sandbox), the scan keeps
the bypass-plus-OS-sandbox path.
"""
from __future__ import annotations

import functools
import json
import platform
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

from packaging.version import InvalidVersion, Version

from quodeq.shared.constants import SYSTEM_WINDOWS

_BYPASS_FLAG = "--dangerously-bypass-approvals-and-sandbox"
_CONFIG_FLAG = "-c"
_PROFILE = "quodeq_scan"
_MIN_VERSION = Version("0.162.0")  # first version tested with approved MCP tools in read-only
_PROBE_TIMEOUT_S = 20
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")
_MCP_OVERRIDE_PREFIX = "mcp_servers."
_APPROVE_TOOLS = ', default_tools_approval_mode = "approve"}'


def _toml_str(value: str) -> str:
    return json.dumps(value)  # a JSON string is a valid TOML basic string


def plain_read_only_args() -> list[str]:
    """``-c`` overrides for read-only without read limits: no writes and no
    network, home readable. Windows refuses restricted reads unless its
    elevated sandbox backend is installed, but runs this."""
    return [_CONFIG_FLAG, 'approval_policy="never"']


def profile_args(home: Path, readable: list[Path]) -> list[str]:
    """``-c`` overrides selecting a read-only profile with *home* unreadable
    except *readable*, and no approval prompts."""
    entries = [f"{_toml_str(str(home))} = \"none\""]
    entries += [f"{_toml_str(str(p))} = \"read\"" for p in dict.fromkeys(readable)]
    overrides = [
        'approval_policy="never"',
        f'default_permissions="{_PROFILE}"',
        f'permissions.{_PROFILE}.extends=":read-only"',
        f"permissions.{_PROFILE}.filesystem={{{', '.join(entries)}}}",
    ]
    return [arg for override in overrides for arg in (_CONFIG_FLAG, override)]


def native_args(args: list[str], profile: list[str]) -> list[str]:
    """*args* with the bypass swapped for Codex's read-only sandbox and the
    findings server's tools pre-approved."""
    out: list[str] = []
    for arg in args:
        if arg == _BYPASS_FLAG:
            out += ["-s", "read-only", *profile]
        elif arg.startswith(_MCP_OVERRIDE_PREFIX) and arg.endswith("}"):
            out.append(arg[:-1] + _APPROVE_TOOLS)
        else:
            out.append(arg)
    return out


def _version(binary: str, env: Mapping[str, str]) -> Version | None:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=_PROBE_TIMEOUT_S, env=dict(env), check=False).stdout
        match = _VERSION_RE.search(out)
        return Version(match.group(1)) if match else None
    except (OSError, subprocess.SubprocessError, InvalidVersion):
        return None


def _probe_command(listed: Path, sample: Path) -> list[str]:
    """List *listed* and read *sample*, as the agent's shell would. On
    Windows each part is its own argument: embedded quotes reach cmd.exe
    escaped (\\"), which it rejects."""
    if platform.system() == SYSTEM_WINDOWS:
        return ["cmd.exe", "/c", "dir", str(listed), "&&", "type", str(sample)]
    return ["/bin/sh", "-c", 'ls "$1" >/dev/null && cat "$2"', "sh", str(listed), str(sample)]


def native_sandbox_works(
    binary: str, profile: list[str], listed: Path, sample: Path, env: Mapping[str, str],
) -> bool:
    """Whether this Codex can run the scan profile here: recent enough, and
    listing *listed* and reading *sample* (a repo file) succeed inside it."""
    return _probe(binary, tuple(profile), listed, sample, tuple(sorted(env.items())))


@functools.cache
def _probe(binary: str, profile: tuple[str, ...], listed: Path, sample: Path,
           env: tuple[tuple[str, str], ...]) -> bool:
    env_map = dict(env)
    version = _version(binary, env_map)
    if version is None or version < _MIN_VERSION:
        return False
    try:
        probe = subprocess.run(
            [binary, "sandbox", *profile, "--", *_probe_command(listed, sample)],
            capture_output=True, timeout=_PROBE_TIMEOUT_S, env=env_map, cwd=sample.parent, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0 and bool(probe.stdout)
