"""Data-layer env seams: an injected mapping is the only source read.

Each seam is checked twice -- with a value injected, and with an injected
``{}`` while the process environment carries a different value, which must
be ignored.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.data.cache_store.local import LocalFileBackend, default_cache_root
from quodeq.data.fs.repo_clone import _DEFAULT_CLONE_TIMEOUT_S, GitCloneClient, _get_clone_timeout
from quodeq.data.fs.shared_repo import _cache_base, _git_env


class TestDefaultCacheRoot:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert default_cache_root({"QUODEQ_CACHE_ROOT": str(injected)}) == injected / "results"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        assert default_cache_root({}) == Path.home() / ".quodeq" / "cache" / "results"


class TestLocalFileBackendRoot:
    def test_takes_its_root_from_the_injected_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        backend = LocalFileBackend(enable_index=False, env={"QUODEQ_CACHE_ROOT": str(injected)})
        assert backend._root == injected / "results"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        backend = LocalFileBackend(enable_index=False, env={})
        assert backend._root == Path.home() / ".quodeq" / "cache" / "results"


class TestCloneTimeout:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_GIT_CLONE_TIMEOUT", "11")
        assert _get_clone_timeout({"QUODEQ_GIT_CLONE_TIMEOUT": "22"}) == 22

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_GIT_CLONE_TIMEOUT", "11")
        assert _get_clone_timeout({}) == _DEFAULT_CLONE_TIMEOUT_S


class TestGitCloneClientEnv:
    """The client passes its constructed env to git, with the LFS/locale pins on top."""

    def _captured_env(self, monkeypatch, client: GitCloneClient, method: str) -> dict[str, str]:
        seen: dict[str, str] = {}

        def fake_run(argv, **kwargs):
            seen.update(kwargs["env"])
            return None

        monkeypatch.setattr("quodeq.data.fs.repo_clone.subprocess.run", fake_run)
        if method == "progress":
            client.clone_progress("url", Path("dest"), [], timeout_s=1)
        else:
            client.clone_legacy("url", Path("dest"), timeout_s=1)
        return seen

    def test_progress_clone_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        client = GitCloneClient({"VAR": "from-env"})
        env = self._captured_env(monkeypatch, client, "progress")
        assert env["VAR"] == "from-env"
        assert env["GIT_LFS_SKIP_SMUDGE"] == "1"
        assert env["LC_ALL"] == "C"

    def test_progress_clone_with_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        env = self._captured_env(monkeypatch, GitCloneClient({}), "progress")
        assert "VAR" not in env

    def test_legacy_clone_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        env = self._captured_env(monkeypatch, GitCloneClient({"VAR": "from-env"}), "legacy")
        assert env["VAR"] == "from-env"

    def test_legacy_clone_with_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        env = self._captured_env(monkeypatch, GitCloneClient({}), "legacy")
        assert "VAR" not in env


class TestGitEnv:
    def test_uses_the_injected_value(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        env = _git_env({"VAR": "from-env"})
        assert env["VAR"] == "from-env"
        assert env["GIT_TERMINAL_PROMPT"] == "0"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch):
        monkeypatch.setenv("VAR", "from-process")
        assert "VAR" not in _git_env({})


class TestSharedCacheBase:
    def test_uses_the_injected_value(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        injected = tmp_path / "from-env"
        assert _cache_base({"QUODEQ_CACHE_ROOT": str(injected)}) == injected / "shared"

    def test_empty_injected_env_ignores_the_process(self, monkeypatch, tmp_path):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
        assert _cache_base({}) == Path.home() / ".quodeq" / "cache" / "shared"
