"""Git clone helpers for the filesystem action provider."""

from __future__ import annotations

import json
import os
import subprocess as _subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from quodeq.data.fs.repo_validation import _PRIVATE_HOST_RE, _resolves_to_private
from quodeq.shared.repo_handler import is_valid_repo_url

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
_NOT_FOUND_MARKERS = ("Repository not found", "does not exist", "could not find")
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
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
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
    except OSError as exc:
        raise CloneError("disk", f"git clone could not start: {exc}") from exc


def clone_to_local(
    reports_dir: str, project: str, destination: str, *, get_project_info_fn: Any,
) -> dict[str, Any] | None:
    """Clone an online project's repo to a local path and update its metadata."""
    reports_root = Path(reports_dir).resolve()
    info_path = (reports_root / project / "repository_info.json").resolve()
    if not info_path.is_relative_to(reports_root) or not info_path.exists():
        return None
    try:
        info = json.loads(info_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    url = info.get("path", "")
    if info.get("location") != "online" or not is_valid_repo_url(url):
        return None

    dest_dir = Path(destination).resolve()
    if not dest_dir.is_dir():
        return None

    if _PRIVATE_HOST_RE.match(url):
        return None
    if url.startswith("http"):
        hostname = urllib.parse.urlparse(url).hostname or ""
        if hostname and _resolves_to_private(hostname):
            return None

    project_name = info.get("name", url.split("/")[-1].replace(".git", ""))
    # Sanitize project name to prevent path traversal
    if "/" in project_name or "\\" in project_name or ".." in project_name:
        return None
    clone_dest = dest_dir / project_name
    if not clone_dest.resolve().is_relative_to(dest_dir.resolve()):
        return None

    if clone_dest.exists():
        return None

    try:
        run_git_clone(url, clone_dest)
    except CloneError:
        return None

    resolved_clone = str(clone_dest.resolve())
    info["path"] = resolved_clone
    info["location"] = "local"
    try:
        info_path.write_text(json.dumps(info, indent=2))
    except OSError:
        return None

    return get_project_info_fn(reports_dir, project)
