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
the bypass-plus-OS-sandbox path. What the repo holds must not decide that:
see :func:`probe_sample`.
"""
from __future__ import annotations

import functools
import json
import os
import platform
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from packaging.version import InvalidVersion, Version

from quodeq.core.secret_files import secret_file_kind
from quodeq.shared.constants import GIT_DIR_NAME, SYSTEM_WINDOWS
from quodeq.shared.win_launch import launch_argv, program_argv

_BYPASS_FLAG = "--dangerously-bypass-approvals-and-sandbox"
_CONFIG_FLAG = "-c"
_PROFILE = "quodeq_scan"
_MIN_VERSION = Version("0.162.0")  # first version tested with approved MCP tools in read-only
_PROBE_TIMEOUT_S = 20
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")
_MCP_OVERRIDE_PREFIX = "mcp_servers."
_APPROVE_TOOLS = ', default_tools_approval_mode = "approve"}'
SAMPLE_MAX_BYTES = 64 * 1024  # the probe prints its sample
SAMPLE_SCAN_LIMIT = 2000  # files looked at before giving up on the repo
_SAMPLE_NAME_RE = re.compile(r"[A-Za-z0-9._-]+")  # nothing sh or cmd.exe acts on
_OWN_SAMPLE = Path(__file__).resolve()


def _toml_str(value: str) -> str:
    return json.dumps(value)  # a JSON string is a valid TOML basic string


def plain_read_only_args(unreadable: Sequence[Path] = ()) -> list[str]:
    """``-c`` overrides for read-only with no read limits but *unreadable*:
    no writes and no network, home readable. Windows refuses restricted
    reads unless its elevated sandbox backend is installed, but runs this
    when there is nothing to deny; a probe decides."""
    if not unreadable:
        return [_CONFIG_FLAG, 'approval_policy="never"']
    return _profile(_unreadable_entries(unreadable))


def _unreadable_entries(paths: Sequence[Path]) -> list[str]:
    return [f"{_toml_str(str(p))} = \"none\"" for p in dict.fromkeys(paths)]


def profile_args(home: Path, readable: list[Path], unreadable: Sequence[Path] = ()) -> list[str]:
    """``-c`` overrides selecting a read-only profile with *home* unreadable
    except *readable*, *unreadable* files unreadable even inside those, and
    no approval prompts."""
    entries = [f"{_toml_str(str(home))} = \"none\""]
    entries += [f"{_toml_str(str(p))} = \"read\"" for p in dict.fromkeys(readable)]
    return _profile([*entries, *_unreadable_entries(unreadable)])


def _profile(entries: list[str]) -> list[str]:
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
        out = subprocess.run(launch_argv([binary, "--version"], env), capture_output=True, text=True,
                             encoding="utf-8", errors="replace",
                             timeout=_PROBE_TIMEOUT_S, env=dict(env), check=False).stdout
        match = _VERSION_RE.search(out)
        return Version(match.group(1)) if match else None
    except (OSError, subprocess.SubprocessError, InvalidVersion):
        return None


def _probe_commands(listed: Path, sample: Path) -> list[list[str]]:
    """List *listed* and read *sample*, as the agent's shell would. On
    Windows they are two runs, each part its own argument: npm's ``codex.cmd``
    goes through cmd.exe, which would run anything after ``&&`` outside the
    sandbox, and embedded quotes reach cmd.exe escaped (\\"), which it rejects."""
    if platform.system() == SYSTEM_WINDOWS:
        return [program_argv(["cmd.exe", "/c", "dir", str(listed)]),
                program_argv(["cmd.exe", "/c", "type", str(sample)])]
    return [["/bin/sh", "-c", 'ls "$1" >/dev/null && cat "$2"', "sh", str(listed), str(sample)]]


def _usable_sample(path: Path, name: str) -> bool:
    """Whether the probe's verdict on *path* says something about the sandbox
    and nothing about the file: a regular file (a link could point at one the
    profile denies), not empty and small (the probe must print it, in time),
    readable outside the sandbox, with a name no shell reads as syntax, and
    not a credential file (the profile denies those on purpose)."""
    if not _SAMPLE_NAME_RE.fullmatch(name) or secret_file_kind(name) is not None:
        return False
    try:
        info = path.lstat()
    except OSError:
        return False
    return (stat.S_ISREG(info.st_mode) and 0 < info.st_size <= SAMPLE_MAX_BYTES
            and os.access(path, os.R_OK))


def probe_sample(repo: Path) -> Path:
    """The file the probe reads: the first usable one in *repo*, its root
    first, else this module's own source, which every scan profile can read.

    The repo's author controls its files, so none of them may decide the
    verdict: an empty or huge first file, a link or an odd name would fail
    every profile and send the scan to the bypass. With Quodeq's own file
    the probe still proves the sandbox runs here, only not that it reads
    the repo, which then holds nothing it could prove that with."""
    seen = 0
    for dirpath, dirnames, filenames in os.walk(repo, onerror=lambda _exc: None):
        dirnames[:] = sorted(d for d in dirnames if d != GIT_DIR_NAME and _SAMPLE_NAME_RE.fullmatch(d))
        for name in sorted(filenames):
            seen += 1
            if seen > SAMPLE_SCAN_LIMIT:
                return _OWN_SAMPLE
            if _usable_sample(Path(dirpath) / name, name):
                return Path(dirpath) / name
    return _OWN_SAMPLE


def native_sandbox_works(
    binary: str, profile: list[str], listed: Path, sample: Path, env: Mapping[str, str],
    cwd: Path | None = None,
) -> bool:
    """Whether this Codex can run the scan profile here: recent enough, and
    listing *listed* and reading *sample* (see :func:`probe_sample`) succeed
    inside it, run from *cwd* (the sample's folder when not given)."""
    return _probe(binary, tuple(profile), listed, sample, tuple(sorted(env.items())),
                  cwd or sample.parent)


@functools.cache
def _probe(binary: str, profile: tuple[str, ...], listed: Path, sample: Path,
           env: tuple[tuple[str, str], ...], cwd: Path) -> bool:
    env_map = dict(env)
    version = _version(binary, env_map)
    if version is None or version < _MIN_VERSION:
        return False
    try:
        probes = [subprocess.run(
            launch_argv([binary, "sandbox", *profile, "--", *command], env_map),
            capture_output=True, timeout=_PROBE_TIMEOUT_S, env=env_map, cwd=cwd, check=False)
            for command in _probe_commands(listed, sample)]
    except (OSError, subprocess.SubprocessError):
        return False
    return all(probe.returncode == 0 and probe.stdout for probe in probes)
