import subprocess
from pathlib import Path

import pytest

from quodeq.data.fs.repo_handler import prepare_repository
from quodeq.shared.utils import is_repo_url


def test_is_repo_url():
    with pytest.raises(ValueError, match="Cleartext HTTP"):
        is_repo_url("http://example.com/repo.git")
    assert is_repo_url("https://example.com/repo.git")
    assert is_repo_url("git@example.com:repo.git")
    assert not is_repo_url("/local/path/to/repo")


def test_prepare_repository_url_uses_cache(monkeypatch, tmp_path: Path):
    """A URL routes through the persistent online cache.

    The online cache (``context/online_cache.py``) is a separate
    collaborator from ``GitCloneClient`` — not exercised at all here since
    the cache "clone" succeeds on the first try — so this test still
    stubs the real ``subprocess.run`` rather than injecting a client.
    """
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

    from quodeq.data.fs.repo_clone import GitCloneClient

    class _FakeClient(GitCloneClient):
        def clone_legacy(self, repo_input, dest, *, timeout_s):
            dest.mkdir(parents=True, exist_ok=True)

    url = "https://example.com/my-repo.git"
    dest = prepare_repository(url, client=_FakeClient())
    assert Path(dest).name == "my-repo"


def test_prepare_repository_falls_back_when_cache_clone_fails(monkeypatch, tmp_path):
    """Cache miss + clone fail -> retry via legacy path so a broken cache
    doesn't take down evals."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.delenv("QUODEQ_DISABLE_ONLINE_CACHE", raising=False)

    from quodeq.data.fs.repo_clone import GitCloneClient

    def fake_run(cmd, check, **kwargs):
        # Only the online cache's own clone attempt reaches real
        # subprocess.run now; the legacy fallback below goes through the
        # injected GitCloneClient instead.
        raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr("subprocess.run", fake_run)

    legacy_calls = {"n": 0}

    class _FakeClient(GitCloneClient):
        def clone_legacy(self, repo_input, dest, *, timeout_s):
            legacy_calls["n"] += 1
            dest.mkdir(parents=True, exist_ok=True)

    dest = prepare_repository("https://example.com/repo.git", client=_FakeClient())
    assert Path(dest).exists()
    assert legacy_calls["n"] == 1


def test_prepare_repository_clone_failure_raises_when_cache_disabled(monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")

    from quodeq.data.fs.repo_clone import GitCloneClient

    class _FailingClient(GitCloneClient):
        def clone_legacy(self, repo_input, dest, *, timeout_s):
            raise subprocess.CalledProcessError(128, ["git", "clone"])

    with pytest.raises(subprocess.CalledProcessError):
        prepare_repository("https://example.com/bad-repo.git", client=_FailingClient())


def test_cleanup_preserves_cached_clones(monkeypatch, tmp_path):
    """The persistent cache must survive eval-end cleanup."""
    from quodeq.data.fs.repo_handler import cleanup_cloned_repo
    from quodeq.context.online_cache import repo_path_for_url

    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    cached = repo_path_for_url("https://example.com/x.git")
    cached.mkdir(parents=True)

    cleanup_cloned_repo(str(cached))

    assert cached.exists(), "cleanup_cloned_repo wiped the persistent cache"


def test_cleanup_still_removes_legacy_tempdir(monkeypatch, tmp_path):
    from quodeq.data.fs.repo_handler import cleanup_cloned_repo

    legacy = tmp_path / "scratch" / "my-repo"
    legacy.mkdir(parents=True)

    cleanup_cloned_repo(str(legacy))

    assert not legacy.parent.exists()
