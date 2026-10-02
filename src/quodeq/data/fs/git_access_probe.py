"""Pre-clone reachability probe: ``git ls-remote`` with prompts disabled.

Answers "can git reach this URL with this environment?" in seconds, with a
classified reason, so the access ladder (services/github_access.py) can try
the next credential or tell the user exactly what is missing. Never raises.
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from quodeq.config.clone_env import git_probe_timeout_s
from quodeq.data.git_cli import git_env_floor
from quodeq.shared.constants import GIT_BIN
from quodeq.shared.git_errors import GitFailureKind, classify_git_output, output_tail

# GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n (how the ladder hands git a token) exist
# since git 2.31 (March 2021).
MIN_GIT_VERSION: tuple[int, int] = (2, 31)
_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)")
_VERSION_TIMEOUT_S = 5
# `ls-remote --exit-code` exits 2 when no ref matched: an empty repository,
# which is reachable.
_EXIT_NO_MATCHING_REFS = 2


@dataclass(frozen=True)
class ProbeResult:
    """What the probe found. *detail* is git's own output tail, empty when the
    process never produced safe output (timeout, missing binary)."""

    kind: GitFailureKind
    detail: str = ""


def git_version(
    *, env: Mapping[str, str] | None = None, run: Callable[..., object] = subprocess.run,
) -> tuple[int, int] | None:
    """``(major, minor)`` of the git on PATH, or None when it cannot be read."""
    try:
        proc = run(
            [GIT_BIN, "--version"], env=git_env_floor(env), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=_VERSION_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = _VERSION_RE.search(getattr(proc, "stdout", "") or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def _too_old(version: tuple[int, int] | None) -> bool:
    return version is not None and version < MIN_GIT_VERSION


def probe_remote(
    url: str, *, env: Mapping[str, str] | None = None, timeout_s: int | None = None,
    run: Callable[..., object] = subprocess.run,
) -> ProbeResult:
    """Classified reachability of *url* for git running under *env*."""
    version = git_version(env=env, run=run)
    if _too_old(version):
        return ProbeResult(GitFailureKind.GIT_TOO_OLD, f"git {version[0]}.{version[1]}")
    timeout = timeout_s if timeout_s is not None else git_probe_timeout_s(env)
    try:
        proc = run(
            [GIT_BIN, "ls-remote", "--exit-code", "--heads", "--", url],
            env=git_env_floor(env), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(GitFailureKind.TIMEOUT)
    except FileNotFoundError:
        return ProbeResult(GitFailureKind.GIT_MISSING)
    except (OSError, subprocess.SubprocessError):
        return ProbeResult(GitFailureKind.UNKNOWN)
    code = getattr(proc, "returncode", 1)
    if code == 0 or code == _EXIT_NO_MATCHING_REFS:
        return ProbeResult(GitFailureKind.OK)
    output = (getattr(proc, "stdout", "") or "") + (getattr(proc, "stderr", "") or "")
    return ProbeResult(classify_git_output(output), output_tail(output))
