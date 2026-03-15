"""Repository preparation utility — clones remote repos to temporary directories."""
from __future__ import annotations

import atexit
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_REPO_URL_RE = re.compile(
    r"^(https?://[\w.\-]+/[\w.\-/]+(\.git)?|git@[\w.\-]+:[\w.\-/]+(\.git)?)$"
)


def _get_clone_timeout() -> int:
    """Return the git clone timeout, reading the env var lazily."""
    try:
        return int(os.environ.get("QUODEQ_GIT_CLONE_TIMEOUT", "300"))
    except ValueError:
        return 300


def is_valid_repo_url(url: str) -> bool:
    """Return True if *url* matches the expected git repository URL format."""
    return _REPO_URL_RE.match(url) is not None


def prepare_repository(repo_input: str) -> str:
    """Clone a remote repository to a temporary directory and return its path.

    Raises ValueError if the URL does not match the expected git repository format.
    """
    if not _REPO_URL_RE.match(repo_input):
        raise ValueError(f"Invalid repository URL format: {repo_input}. Expected: https://github.com/user/repo or git@github.com:user/repo.git")
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
    atexit.register(shutil.rmtree, tmp_dir, True)
    return str(dest.resolve())
