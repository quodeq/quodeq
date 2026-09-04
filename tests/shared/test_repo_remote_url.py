"""Tests for the pure repo-URL helpers in shared/_repo.

``normalize_remote_url`` is a pure string function (no git, no patching);
the process side lives in ``data/git_cli.py`` and is covered by
``tests/data/test_git_cli.py`` against real repositories.
"""
from __future__ import annotations


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


def test_normalize_https():
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("https://github.com/quodeq/quodeq.git") == "github.com/quodeq/quodeq"


def test_normalize_ssh_colon_form():
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("git@github.com:quodeq/quodeq.git") == "github.com/quodeq/quodeq"


def test_normalize_ssh_scheme():
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("ssh://git@github.com/quodeq/quodeq.git") == "github.com/quodeq/quodeq"


def test_normalize_strips_trailing_slash_and_git():
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("https://github.com/quodeq/quodeq/") == "github.com/quodeq/quodeq"


def test_normalize_empty_returns_none():
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("") is None
    assert normalize_remote_url("   ") is None


def test_normalize_strips_https_userinfo_with_password():
    """HTTPS URLs with embedded user:token@host should strip the userinfo."""
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("https://user:token@github.com/org/repo.git") == "github.com/org/repo"


def test_normalize_strips_https_userinfo_token_only():
    """HTTPS URLs with embedded token@host should strip the token."""
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("https://token@github.com/org/repo.git") == "github.com/org/repo"


def test_normalize_ssh_colon_form_still_works():
    """Confirm that git@host:path normalization is unchanged by userinfo stripping."""
    from quodeq.shared._repo import normalize_remote_url
    assert normalize_remote_url("git@github.com:quodeq/quodeq.git") == "github.com/quodeq/quodeq"
