from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path
import subprocess


def is_repo_url(repo_input: str) -> bool:
    return repo_input.startswith(("http://", "https://", "git@"))


def prepare_repository(repo_input: str) -> str:
    """Clone a remote repository to a temporary directory and return its path."""
    repo_name = repo_input.split("/")[-1].replace(".git", "")
    tmp_dir = tempfile.mkdtemp()
    dest = Path(tmp_dir) / repo_name
    subprocess.run(["git", "clone", repo_input, str(dest)], check=True)
    atexit.register(shutil.rmtree, tmp_dir, True)
    return str(dest.resolve())
