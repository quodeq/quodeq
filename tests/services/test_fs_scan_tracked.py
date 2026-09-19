"""scan_project counts only git-tracked files and reports the rest (#1209).

After #1207 an evaluation scores only what git tracks, so the wizard's
pre-run numbers must come from the same set or the two disagree with no
explanation. Real repositories, no mocks: the filter is git's answer.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quodeq.services._fs_scan import scan_project


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
             "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(repo), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"},
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "tracked.py").write_text("pass\n")
    (tmp_path / "notes.md").write_text("# hi\n")
    _git(tmp_path, "add", "tracked.py", "notes.md")
    _git(tmp_path, "commit", "-q", "-m", "init")
    (tmp_path / "scratch.py").write_text("pass\n")
    (tmp_path / "draft.md").write_text("draft\n")
    return tmp_path


def test_untracked_files_leave_the_counts_and_the_tree(repo: Path) -> None:
    scan = scan_project(repo)
    assert scan.file_tree == ["notes.md", "tracked.py"]
    assert scan.total_files == 2
    assert scan.code_files == 1
    assert scan.languages == {"md": 1, "py": 1}
    assert scan.untracked_files == 2


def test_outside_a_git_work_tree_everything_is_counted(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("pass\n")
    (tmp_path / "b.py").write_text("pass\n")
    scan = scan_project(tmp_path)
    assert scan.total_files == 2
    assert scan.untracked_files == 0


def test_scan_json_carries_the_untracked_count(repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    scan_project(repo, output_dir=out)
    payload = json.loads((out / "scan.json").read_text(encoding="utf-8"))
    assert payload["total_files"] == 2
    assert payload["untracked_files"] == 2
