"""Git clone helpers for the filesystem action provider."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_GIT_CLONE_TIMEOUT_S = 300


def run_git_clone(url: str, clone_dest: Path) -> bool:
    """Execute ``git clone`` for *url* into *clone_dest*."""
    import subprocess as _subprocess

    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        _subprocess.run(
            ["git", "clone", "--progress", url, str(clone_dest)],
            check=True,
            env=env,
            timeout=_GIT_CLONE_TIMEOUT_S,
        )
        return True
    except (_subprocess.CalledProcessError, _subprocess.TimeoutExpired, OSError):
        return False


def clone_to_local(
    reports_dir: str, project: str, destination: str, *, get_project_info_fn: Any,
) -> dict[str, Any] | None:
    """Clone an online project's repo to a local path and update its metadata."""
    from quodeq.shared.repo_handler import is_valid_repo_url

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

    from quodeq.data.fs.repo_handler import _PRIVATE_HOST_RE, _resolves_to_private

    if _PRIVATE_HOST_RE.match(url):
        return None
    if url.startswith("http"):
        import urllib.parse
        hostname = urllib.parse.urlparse(url).hostname or ""
        if hostname and _resolves_to_private(hostname):
            return None

    project_name = info.get("name", url.split("/")[-1].replace(".git", ""))
    clone_dest = dest_dir / project_name

    if clone_dest.exists():
        return None

    if not run_git_clone(url, clone_dest):
        return None

    resolved_clone = str(clone_dest.resolve())
    info["path"] = resolved_clone
    info["location"] = "local"
    try:
        info_path.write_text(json.dumps(info, indent=2))
    except OSError:
        return None

    return get_project_info_fn(reports_dir, project)
