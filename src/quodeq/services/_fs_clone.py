"""Git clone helpers for the filesystem action provider."""

from __future__ import annotations

import errno
import logging
import os
import subprocess as _subprocess
from pathlib import Path

from quodeq.services.shared_repo import remove_clone_dir
from quodeq.shared._env import env_int

_logger = logging.getLogger(__name__)

_GIT_CLONE_TIMEOUT_S = env_int("QUODEQ_GIT_CLONE_TIMEOUT_S", 300, minimum=1)

# One month of slack over the default git churn lookback (git_lookback_months,
# 3) so the boundary commit is never cut off. Raise QUODEQ_CLONE_SHALLOW_MONTHS
# when a project configures a larger lookback; 0 forces full-history clones.
_DEFAULT_SHALLOW_MONTHS = 4


def _shallow_months() -> int:
    raw = os.environ.get("QUODEQ_CLONE_SHALLOW_MONTHS", "")
    try:
        return int(raw) if raw else _DEFAULT_SHALLOW_MONTHS
    except ValueError:
        return _DEFAULT_SHALLOW_MONTHS


class CloneError(RuntimeError):
    """Raised when git clone fails. ``kind`` is one of:
    auth | network | repo_not_found | dest_exists | disk | unknown.

    Inherits from RuntimeError so existing ``except RuntimeError`` blocks
    still catch it. ``retryable`` marks failures where a different clone
    strategy could still succeed (used for the shallow → full fallback).
    """

    def __init__(self, kind: str, message: str, stderr: str = "", *, retryable: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.stderr = stderr
        self.retryable = retryable


_AUTH_MARKERS = (
    "Permission denied",
    "Authentication failed",
    "could not read Username",
    "Host key verification failed",
)
_NETWORK_MARKERS = (
    "Could not resolve host",
    "Connection timed out",
    "Connection refused",
    "Operation timed out",
)
_NOT_FOUND_MARKERS = ("Repository not found", "repository '", "' not found")
_DEST_EXISTS_MARKERS = ("already exists and is not an empty directory",)
_DISK_MARKERS = ("No space left on device", "disk full")


def _classify_stderr(stderr: str) -> str:
    s = stderr or ""
    if any(m in s for m in _AUTH_MARKERS):
        return "auth"
    if any(m in s for m in _NOT_FOUND_MARKERS):
        return "repo_not_found"
    if any(m in s for m in _DEST_EXISTS_MARKERS):
        return "dest_exists"
    if any(m in s for m in _DISK_MARKERS):
        return "disk"
    if any(m in s for m in _NETWORK_MARKERS):
        return "network"
    return "unknown"


# Kinds where a shallow-specific rejection is indistinguishable from a real
# failure (servers answer unsatisfiable --shallow-since requests with generic
# hang-up/protocol errors), so a full clone may still succeed. Deterministic
# kinds (auth, repo_not_found, dest_exists, disk) would fail identically.
_RETRYABLE_KINDS = ("network", "unknown")


def _clone_once(url: str, clone_dest: Path, extra_args: list[str]) -> None:
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "LC_ALL": "C", "LANG": "C"}
    try:
        _subprocess.run(
            ["git", "clone", "--progress", *extra_args, "--", url, str(clone_dest)],
            check=True,
            env=env,
            timeout=_GIT_CLONE_TIMEOUT_S,
            capture_output=True,
        )
    except _subprocess.CalledProcessError as exc:
        raw = exc.stderr
        if isinstance(raw, bytes):
            stderr = raw.decode("utf-8", errors="replace")
        else:
            stderr = raw or ""
        kind = _classify_stderr(stderr)
        raise CloneError(
            kind, f"git clone failed ({kind})", stderr, retryable=kind in _RETRYABLE_KINDS,
        ) from exc
    except _subprocess.TimeoutExpired as exc:
        # Not retryable: the attempt already spent the whole clone timeout,
        # a full clone can only be slower.
        raise CloneError("network", "git clone timed out") from exc
    except FileNotFoundError as exc:
        raise CloneError("unknown", f"git binary not found: {exc}") from exc
    except OSError as exc:
        kind = "disk" if exc.errno == errno.ENOSPC else "unknown"
        raise CloneError(kind, f"git clone could not start: {exc}") from exc


def run_git_clone(url: str, clone_dest: Path) -> None:
    """Execute ``git clone`` for *url* into *clone_dest*. Raises CloneError on failure.

    Clones shallow by default (``--single-branch``, ``--no-tags``,
    ``--shallow-since``): the working copy is evaluated at HEAD and the only
    history consumer is git churn scoring, whose lookback the default window
    covers (see ``_DEFAULT_SHALLOW_MONTHS``). Branch evaluations against such
    a clone rely on ``_cli_resolution._fetch_branch`` fetching the missing
    branch on demand. Shallow requests the remote cannot satisfy (e.g. no
    commits inside the window) fall back to one full clone. A shallow working
    copy can be completed manually with ``git fetch --unshallow``.
    """
    months = _shallow_months()
    if months <= 0:
        _clone_once(url, clone_dest, [])
        return
    try:
        _clone_once(
            url,
            clone_dest,
            ["--single-branch", "--no-tags", f"--shallow-since={months} months ago"],
        )
    except CloneError as exc:
        if not exc.retryable:
            raise
        _logger.info("shallow clone of %s failed (%s), retrying with full history", url, exc.kind)
        # git usually removes the dest it created on failure, but not when
        # killed or on checkout-phase errors; a leftover partial dir would
        # turn the retry into a bogus dest_exists failure.
        remove_clone_dir(clone_dest)
        _clone_once(url, clone_dest, [])
