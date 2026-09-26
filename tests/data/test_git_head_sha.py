"""``git_head_sha`` returns the checked-out commit of a local repo, else None."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from quodeq.data.git_cli import git_head_sha

_SHA_LENGTH = 40


def _init_repo(path: Path) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x", "HOME": str(path)}
    subprocess.run(["git", "init", "-q", str(path)], check=True, env=env)
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "a.txt"], check=True, env=env)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "one"], check=True, env=env)


def test_git_head_sha_reads_head(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    sha = git_head_sha(str(tmp_path))
    assert sha is not None and len(sha) == _SHA_LENGTH


def test_git_head_sha_none_outside_repo(tmp_path: Path) -> None:
    assert git_head_sha(str(tmp_path)) is None
