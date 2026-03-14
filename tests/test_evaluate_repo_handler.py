import subprocess
from pathlib import Path

import pytest

from quodeq.shared.repo_handler import prepare_repository
from quodeq.shared.utils import is_repo_url


def test_is_repo_url():
    assert is_repo_url("http://example.com/repo.git")
    assert is_repo_url("https://example.com/repo.git")
    assert is_repo_url("git@example.com:repo.git")
    assert not is_repo_url("/local/path/to/repo")


def test_prepare_repository_url_creates_tmp(monkeypatch, tmp_path: Path):
    called = {}

    def fake_run(cmd, check, **kwargs):
        called["cmd"] = cmd
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("subprocess.run", fake_run)

    url = "https://example.com/my-repo.git"
    dest = prepare_repository(url)

    assert Path(dest).name == "my-repo"
    assert Path(dest).exists()


def test_prepare_repository_clone_failure(monkeypatch):
    def fake_run(cmd, check, **kwargs):
        raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        prepare_repository("https://example.com/bad-repo.git")
