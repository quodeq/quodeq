"""Tests for git_remote_url and project_name_from_repo edge cases."""
from __future__ import annotations

import subprocess
from unittest.mock import patch


def test_project_name_resolves_dot_to_basename(tmp_path, monkeypatch):
    """Path('.') should resolve to the current directory's basename, not empty."""
    from quodeq.shared._repo import project_name_from_repo
    project = tmp_path / "my-project"
    project.mkdir()
    monkeypatch.chdir(project)
    assert project_name_from_repo(".") == "my-project"


def test_project_name_url_unchanged():
    from quodeq.shared._repo import project_name_from_repo
    assert project_name_from_repo("https://github.com/quodeq/quodeq.git") == "quodeq"


def test_git_remote_url_normalizes_https():
    from quodeq.shared._repo import git_remote_url
    mock = subprocess.CompletedProcess(["git"], 0, stdout="https://github.com/quodeq/quodeq.git\n", stderr="")
    with patch("subprocess.run", return_value=mock):
        assert git_remote_url("/any/path") == "github.com/quodeq/quodeq"


def test_git_remote_url_normalizes_ssh():
    from quodeq.shared._repo import git_remote_url
    mock = subprocess.CompletedProcess(["git"], 0, stdout="git@github.com:quodeq/quodeq.git\n", stderr="")
    with patch("subprocess.run", return_value=mock):
        assert git_remote_url("/any/path") == "github.com/quodeq/quodeq"


def test_git_remote_url_normalizes_ssh_scheme():
    from quodeq.shared._repo import git_remote_url
    mock = subprocess.CompletedProcess(
        ["git"], 0, stdout="ssh://git@github.com/quodeq/quodeq.git\n", stderr=""
    )
    with patch("subprocess.run", return_value=mock):
        assert git_remote_url("/any/path") == "github.com/quodeq/quodeq"


def test_git_remote_url_strips_trailing_slash_and_git():
    from quodeq.shared._repo import git_remote_url
    mock = subprocess.CompletedProcess(["git"], 0, stdout="https://github.com/quodeq/quodeq/\n", stderr="")
    with patch("subprocess.run", return_value=mock):
        assert git_remote_url("/any/path") == "github.com/quodeq/quodeq"


def test_git_remote_url_returns_none_when_not_a_repo():
    from quodeq.shared._repo import git_remote_url
    error = subprocess.CalledProcessError(128, ["git"], stderr="not a git repo")
    with patch("subprocess.run", side_effect=error):
        assert git_remote_url("/any/path") is None


def test_git_remote_url_returns_none_when_git_missing():
    from quodeq.shared._repo import git_remote_url
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert git_remote_url("/any/path") is None


def test_git_remote_url_returns_none_on_empty_output():
    from quodeq.shared._repo import git_remote_url
    mock = subprocess.CompletedProcess(["git"], 0, stdout="\n", stderr="")
    with patch("subprocess.run", return_value=mock):
        assert git_remote_url("/any/path") is None
