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
    r"^(https?://[\w.\-]+/[\w.\-/]+\.git|git@[\w.\-]+:[\w.\-/]+\.git)$"
)


def prepare_repository(repo_input: str) -> str:
    """Clone a remote repository to a temporary directory and return its path.

    Raises ValueError if the URL does not match the expected git repository format.
    """
    if not _REPO_URL_RE.match(repo_input):
        raise ValueError(f"Invalid repository URL format: {repo_input}")
    repo_name = repo_input.split("/")[-1].replace(".git", "")
    tmp_dir = tempfile.mkdtemp()
    dest = Path(tmp_dir) / repo_name
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    subprocess.run(["git", "clone", repo_input, str(dest)], check=True, env=env)
    atexit.register(shutil.rmtree, tmp_dir, True)
    return str(dest.resolve())
