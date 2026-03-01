from pathlib import Path

import pytest

from codecompass.evaluate.lib.repo_handler import is_repo_url, prepare_repository


def test_is_repo_url():
    assert is_repo_url("http://example.com/repo.git")
    assert is_repo_url("https://example.com/repo.git")
    assert is_repo_url("git@example.com:repo.git")
    assert not is_repo_url("/local/path/to/repo")


def test_prepare_repository_local_copies_to_tmp(tmp_path: Path, monkeypatch):
    # Set up a fake local repo with some files and a gitignored file
    repo = tmp_path / "my-repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hello')")
    (repo / "secret.env").write_text("SECRET=abc")
    (repo / ".gitignore").write_text("secret.env\n")

    def fake_git(cmd, cwd, capture_output, text):
        # Simulate `git ls-files --others --ignored ...` returning secret.env
        class R:
            returncode = 0
            stdout = "secret.env\n"
        return R()

    monkeypatch.setattr("subprocess.run", fake_git)

    dest = prepare_repository(str(repo))
    dest_path = Path(dest)

    # Should be copied to tmp/, not the original path
    assert dest_path != repo.resolve()
    assert dest_path.name == "my-repo"
    assert (dest_path / "main.py").exists()
    assert (dest_path / ".gitignore").exists()
    # Gitignored file should be stripped
    assert not (dest_path / "secret.env").exists()
    # .git dir should not be copied
    assert not (dest_path / ".git").exists()


def test_prepare_repository_local_missing_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        prepare_repository(str(tmp_path / "nonexistent"))


def test_prepare_repository_url_creates_tmp(monkeypatch, tmp_path: Path):
    called = {}

    def fake_run(cmd, check):
        called["cmd"] = cmd
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("subprocess.run", fake_run)

    url = "https://example.com/my-repo.git"
    dest = prepare_repository(url)

    assert Path(dest).parent.name == "tmp"
    assert Path(dest).exists()
