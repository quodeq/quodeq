import subprocess
from pathlib import Path

import pytest

from quodeq.shared.repo_handler import prepare_repository
from quodeq.shared.utils import is_repo_url


def test_is_repo_url():
    with pytest.raises(ValueError, match="Cleartext HTTP"):
        is_repo_url("http://example.com/repo.git")
    assert is_repo_url("https://example.com/repo.git")
    assert is_repo_url("git@example.com:repo.git")
    assert not is_repo_url("/local/path/to/repo")


def test_prepare_repository_url_uses_cache(monkeypatch, tmp_path: Path):
    """A URL routes through the persistent online cache."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.delenv("QUODEQ_DISABLE_ONLINE_CACHE", raising=False)

    def fake_run(cmd, check, **kwargs):
        dest = Path(cmd[-1])
        (dest / ".git").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("subprocess.run", fake_run)

    url = "https://example.com/my-repo.git"
    dest = prepare_repository(url)

    # Cache layout: <cache>/<url_hash>/repo
    assert Path(dest).name == "repo"
    assert Path(dest).exists()
    assert Path(dest).is_relative_to(tmp_path / "cache")


def test_prepare_repository_legacy_tempdir_when_cache_disabled(monkeypatch):
    """`QUODEQ_DISABLE_ONLINE_CACHE=1` keeps the old mkdtemp behavior."""
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")

    def fake_run(cmd, check, **kwargs):
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("subprocess.run", fake_run)

    url = "https://example.com/my-repo.git"
    dest = prepare_repository(url)
    assert Path(dest).name == "my-repo"


def test_prepare_repository_falls_back_when_cache_clone_fails(monkeypatch, tmp_path):
    """Cache miss + clone fail -> retry via legacy path so a broken cache
    doesn't take down evals."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.delenv("QUODEQ_DISABLE_ONLINE_CACHE", raising=False)

    call_count = {"n": 0}

    def fake_run(cmd, check, **kwargs):
        call_count["n"] += 1
        # First (cache) clone fails, second (legacy) clone succeeds.
        if call_count["n"] == 1:
            raise subprocess.CalledProcessError(128, cmd)
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("subprocess.run", fake_run)

    dest = prepare_repository("https://example.com/repo.git")
    assert Path(dest).exists()
    assert call_count["n"] == 2


def test_prepare_repository_clone_failure_raises_when_cache_disabled(monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")

    def fake_run(cmd, check, **kwargs):
        raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr("subprocess.run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        prepare_repository("https://example.com/bad-repo.git")


def test_cleanup_preserves_cached_clones(monkeypatch, tmp_path):
    """The persistent cache must survive eval-end cleanup."""
    from quodeq.shared.repo_handler import cleanup_cloned_repo
    from quodeq.context.online_cache import repo_path_for_url

    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    cached = repo_path_for_url("https://example.com/x.git")
    cached.mkdir(parents=True)

    cleanup_cloned_repo(str(cached))

    assert cached.exists(), "cleanup_cloned_repo wiped the persistent cache"


def test_cleanup_still_removes_legacy_tempdir(monkeypatch, tmp_path):
    from quodeq.shared.repo_handler import cleanup_cloned_repo

    legacy = tmp_path / "scratch" / "my-repo"
    legacy.mkdir(parents=True)

    cleanup_cloned_repo(str(legacy))

    assert not legacy.parent.exists()
