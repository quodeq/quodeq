import subprocess

import pytest

from quodeq.data.fs.repo_validation import (
    is_valid_repo_url,
    local_path_from_file_url_remainder,
    validate_remote_url,
)
from quodeq.shared.git_errors import NOT_A_GIT_REPO_MESSAGE, NotAGitRepoError


def _bare(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True, timeout=30)
    return origin


def test_file_url_to_a_bare_repo_under_home_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    validate_remote_url((_bare(tmp_path)).as_uri())


def test_file_url_to_a_worktree_repo_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    work = tmp_path / "work"
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True, timeout=30)
    validate_remote_url((work).as_uri())


def test_file_url_is_url_decoded(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    spaced = tmp_path / "my repo.git"
    subprocess.run(["git", "init", "--bare", str(spaced)], check=True, capture_output=True, timeout=30)
    url = spaced.as_uri()
    assert "%20" in url
    validate_remote_url(url)


def test_file_url_to_a_plain_folder_is_refused_as_not_a_git_repo(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "plain").mkdir()
    with pytest.raises(ValueError, match="not a git repository") as caught:
        validate_remote_url((tmp_path / 'plain').as_uri())
    assert isinstance(caught.value, NotAGitRepoError)
    assert str(caught.value) == NOT_A_GIT_REPO_MESSAGE
    assert str(tmp_path) not in str(caught.value)


def test_file_url_to_a_missing_path_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    with pytest.raises(ValueError, match="not a git repository"):
        validate_remote_url((tmp_path / 'nope').as_uri())


def test_file_url_outside_home_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    (tmp_path / "home").mkdir()
    with pytest.raises(ValueError) as caught:
        validate_remote_url((_bare(tmp_path)).as_uri())
    assert str(tmp_path) not in str(caught.value)


def test_file_url_escaping_home_through_dotdot_is_refused(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    origin = _bare(tmp_path)
    with pytest.raises(ValueError):
        validate_remote_url(home.as_uri() + f"/../{origin.name}")


def test_only_the_absolute_form_is_valid(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    _bare(tmp_path)
    for url in ("file://origin.git", f"file://localhost{tmp_path}/origin.git", "file://", "file://q/../origin.git"):
        with pytest.raises(ValueError, match="absolute") as caught:
            validate_remote_url(url)
        assert not isinstance(caught.value, NotAGitRepoError)


def test_a_trailing_dot_segment_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    origin = _bare(tmp_path)
    for suffix in ("/.", "/..", "/sub/..", "/./", "/%2e", "/%2E%2E"):
        with pytest.raises(ValueError, match="absolute"):
            validate_remote_url(origin.as_uri() + suffix)


def test_a_symlink_under_home_to_a_repo_outside_home_is_refused(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    outside = _bare(tmp_path)
    (home / "link.git").symlink_to(outside)
    with pytest.raises(ValueError, match="home folder"):
        validate_remote_url((home / "link.git").as_uri())


def test_a_windows_drive_remainder_loses_the_leading_slash_only_on_windows():
    # Path.as_uri() on Windows writes file:///C:/Users/..., whose remainder
    # starts with a slash no Windows path has.
    assert local_path_from_file_url_remainder("/C:/Users/me/evals.git", windows=True) == "C:/Users/me/evals.git"
    assert local_path_from_file_url_remainder("/C:\\Users\\me", windows=True) == "C:\\Users\\me"
    assert local_path_from_file_url_remainder("/Users/me/evals.git", windows=True) == "/Users/me/evals.git"
    assert local_path_from_file_url_remainder("/C:/Users/me", windows=False) == "/C:/Users/me"


def test_file_urls_are_not_valid_for_the_project_relocate_check(tmp_path):
    assert not is_valid_repo_url((tmp_path).as_uri())
