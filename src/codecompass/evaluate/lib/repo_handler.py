from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path
import os
import subprocess


from codecompass.utils import is_repo_url as is_repo_url  # re-export from shared location


def prepare_repository(repo_input: str) -> str:
    """Clone a remote repository to a temporary directory and return its path."""
    repo_name = repo_input.split("/")[-1].replace(".git", "")
    tmp_dir = tempfile.mkdtemp()
    dest = Path(tmp_dir) / repo_name
    env = {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"}
    subprocess.run(["git", "clone", repo_input, str(dest)], check=True, env=env)
    atexit.register(shutil.rmtree, tmp_dir, True)
    return str(dest.resolve())
