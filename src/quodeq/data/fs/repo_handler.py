"""Repository preparation utility — clones remote repos to temporary directories."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_logger = logging.getLogger(__name__)

_REPO_URL_RE = re.compile(
    r"^(https?://[\w.\-]+/[\w.\-/]+(\.git)?|git@[\w.\-]+:[\w.\-/]+(\.git)?)$"
)

# IP-like hostnames that must be rejected to prevent SSRF via git clone.
_PRIVATE_HOST_RE = re.compile(
    r"^https?://(10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+|169\.254\.\d+\.\d+|127\.\d+\.\d+\.\d+|localhost)[:/]"
)


_DEFAULT_CLONE_TIMEOUT_S = 300


def _get_clone_timeout(env: dict[str, str] | None = None) -> int:
    """Return the git clone timeout, reading the env var lazily."""
    try:
        return int((env or os.environ).get("QUODEQ_GIT_CLONE_TIMEOUT", str(_DEFAULT_CLONE_TIMEOUT_S)))
    except ValueError:
        return _DEFAULT_CLONE_TIMEOUT_S


def is_valid_repo_url(url: str) -> bool:
    """Return True if *url* matches the expected git repository URL format."""
    return _REPO_URL_RE.match(url) is not None


def prepare_repository(repo_input: str) -> str:
    """Clone a remote repository to a temporary directory and return its path.

    Raises ValueError if the URL does not match the expected git repository format.
    """
    if not _REPO_URL_RE.match(repo_input):
        raise ValueError(f"Invalid repository URL format: {repo_input}. Expected: https://github.com/user/repo or git@github.com:user/repo.git")
    if _PRIVATE_HOST_RE.match(repo_input):
        raise ValueError("Repository URLs pointing to private/internal addresses are not allowed")
    repo_name = repo_input.split("/")[-1].replace(".git", "")
    tmp_dir = tempfile.mkdtemp()
    dest = Path(tmp_dir) / repo_name
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    try:
        subprocess.run(
            ["git", "clone", repo_input, str(dest)],
            check=True, env=env, timeout=_get_clone_timeout(),
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return str(dest.resolve())


def cleanup_cloned_repo(repo_path: str) -> None:
    """Remove the temporary clone directory for *repo_path*.

    Call this after the evaluation completes to free disk space promptly
    instead of accumulating temp directories until process exit.
    """
    parent = str(Path(repo_path).resolve().parent)
    try:
        shutil.rmtree(parent, ignore_errors=True)
    except OSError as exc:
        _logger.warning("Failed to clean up temp repo dir %s: %s", parent, exc)
