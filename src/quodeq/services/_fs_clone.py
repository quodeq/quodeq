"""Git clone helpers for the filesystem action provider."""

from __future__ import annotations

import errno
import os
import subprocess as _subprocess
from pathlib import Path

_GIT_CLONE_TIMEOUT_S = int(os.environ.get("QUODEQ_GIT_CLONE_TIMEOUT_S", "300"))


class CloneError(RuntimeError):
    """Raised when git clone fails. ``kind`` is one of:
    auth | network | repo_not_found | dest_exists | disk | unknown.

    Inherits from RuntimeError so existing ``except RuntimeError`` blocks
    still catch it.
    """

    def __init__(self, kind: str, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.stderr = stderr


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


def run_git_clone(url: str, clone_dest: Path) -> None:
    """Execute ``git clone`` for *url* into *clone_dest*. Raises CloneError on failure."""
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "LC_ALL": "C", "LANG": "C"}
    try:
        _subprocess.run(
            ["git", "clone", "--progress", "--", url, str(clone_dest)],
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
        raise CloneError(kind, f"git clone failed ({kind})", stderr) from exc
    except _subprocess.TimeoutExpired as exc:
        raise CloneError("network", "git clone timed out") from exc
    except FileNotFoundError as exc:
        raise CloneError("unknown", f"git binary not found: {exc}") from exc
    except OSError as exc:
        kind = "disk" if exc.errno == errno.ENOSPC else "unknown"
        raise CloneError(kind, f"git clone could not start: {exc}") from exc
