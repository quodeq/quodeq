"""On Windows no helper program is started out of the current directory.

A scan, ``quodeq review`` or a dashboard launched inside a repository has
that repository as its current directory, and Windows looks there first
for a program given by bare name. Each case below runs one spawn site with
Windows lookup simulated, a decoy program in the current directory and the
installed one on PATH, and checks which of the two would have been started.
"""
from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path

import pytest

from quodeq.analysis.diff_resolver import resolve_diff_files
from quodeq.assistant import worktree
from quodeq.ci import review
from quodeq.data import git_cli
from quodeq.data.fs import git_access_probe, git_stats, git_stream, shared_repo_git
from quodeq.data.fs.repo_clone import GitCloneClient
from quodeq.services.github_gh_cli import gh_status
from quodeq.shared.prereqs import run_version_cmd
from quodeq.terminal.links import detect_editor
from tests._windows_which import windows_which

_PROGRAMS = ("git.exe", "gh.exe", "node.exe", "code.cmd", "uv.exe")
_URL = "https://example.invalid/repo.git"


class _Spawned(OSError):
    """Raised by the fake spawn so no site goes on to use a process."""


class _Windows:
    def __init__(self, installed: Path) -> None:
        self.installed = installed
        self.calls: list[tuple[list[str], dict]] = []

    def spawn(self, argv, *args, **kwargs):
        self.calls.append((list(argv), kwargs))
        raise _Spawned("spawn stopped by the test")

    def started(self) -> list[str]:
        return [argv[0] for argv, _ in self.calls]

    def path_of(self, program: str) -> str:
        return str(self.installed / program)


@pytest.fixture
def windows(tmp_path, monkeypatch) -> _Windows:
    repo, installed = tmp_path / "repo", tmp_path / "bin"
    for directory in (repo, installed):
        directory.mkdir()
        for program in _PROGRAMS:
            (directory / program).write_text("", encoding="utf-8")
    monkeypatch.chdir(repo)
    monkeypatch.setenv("PATH", str(installed))
    monkeypatch.setattr("quodeq.shared.win_launch.IS_WIN32", True)
    monkeypatch.setattr("quodeq.shared.win_launch.shutil.which", windows_which)
    state = _Windows(installed)
    monkeypatch.setattr(subprocess, "run", state.spawn)
    monkeypatch.setattr(subprocess, "Popen", state.spawn)
    return state


_GIT_SITES = {
    "git_cli.run_git": lambda w: git_cli.run_git(["status"]),
    "git_cli.stream_log_names": lambda w: list(git_cli.stream_log_names(Path.cwd())),
    "shared_repo_git.run_git": lambda w: shared_repo_git.run_git(["status"]),
    "git_stream.run_git_streaming": lambda w: git_stream.run_git_streaming(
        ["status"], timeout=1, on_line=lambda line: None),
    "git_access_probe.git_version": lambda w: git_access_probe.git_version(run=w.spawn),
    "git_access_probe.probe_remote": lambda w: git_access_probe.probe_remote(_URL, timeout_s=1, run=w.spawn),
    "git_stats.count_commits_since": lambda w: git_stats.count_commits_since(Path.cwd(), "2026-01-01"),
    "repo_clone.clone_progress": lambda w: GitCloneClient().clone_progress(_URL, Path("dest"), [], timeout_s=1),
    "repo_clone.clone_legacy": lambda w: GitCloneClient().clone_legacy(_URL, Path("dest"), timeout_s=1),
    "diff_resolver.resolve_diff_files": lambda w: resolve_diff_files(Path.cwd(), "main"),
    "assistant.worktree.run_git": lambda w: worktree.run_git(["git", "status"]),
}
_GH_SITES = {
    "assistant.worktree.run_git": lambda w: worktree.run_git(["gh", "pr", "create"]),
    "ci.review.detect_pr": lambda w: review.detect_pr(),
    "ci.review.get_github_token": lambda w: review.get_github_token(),
    "github_gh_cli.gh_status": lambda w: gh_status(which=windows_which, run=w.spawn),
}


@pytest.mark.parametrize("site", sorted(_GIT_SITES))
def test_git_is_started_from_path(windows, site):
    with contextlib.suppress(Exception):
        _GIT_SITES[site](windows)
    assert set(windows.started()) == {windows.path_of("git.exe")}


@pytest.mark.parametrize("site", sorted(_GH_SITES))
def test_gh_is_started_from_path(windows, site):
    with contextlib.suppress(Exception):
        _GH_SITES[site](windows)
    assert set(windows.started()) == {windows.path_of("gh.exe")}


def test_version_probe_starts_the_program_from_path_without_a_shell(windows):
    with pytest.raises(_Spawned):
        run_version_cmd(["node", "--version"])
    argv, kwargs = windows.calls[0]
    assert argv == [windows.path_of("node.exe"), "--version"]
    assert not kwargs.get("shell")


def test_version_probe_reports_a_program_only_in_the_current_directory_as_missing(windows):
    (windows.installed / "node.exe").unlink()
    with pytest.raises(FileNotFoundError):
        run_version_cmd(["node", "--version"])
    assert windows.calls == []


def test_editor_is_detected_on_path(windows):
    editor = detect_editor(isfile=lambda path: False, platform="win32")
    assert editor.path == windows.path_of("code.cmd")
