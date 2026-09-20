"""The online clone cache reads its env through the config layer."""
from __future__ import annotations

from pathlib import Path

from quodeq.context import online_cache


def test_cache_root_honours_injected_env(tmp_path: Path, monkeypatch):
    # cache_root() mkdirs what it returns, and the env={} branch falls back to
    # the home directory — pin that to tmp_path so the real ~/.quodeq is never
    # touched. Patching Path.home covers Windows too, where HOME is not read.
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "from-process"))
    assert online_cache.cache_root(env={"QUODEQ_CACHE_ROOT": str(tmp_path)}) == tmp_path / "online"
    # env={} means "nothing set": the exported value must not be consulted.
    assert online_cache.cache_root(env={}) == home / ".quodeq" / "cache" / "online"


def test_cache_disabled_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")
    assert online_cache.cache_disabled(env={"QUODEQ_DISABLE_ONLINE_CACHE": "yes"})
    assert not online_cache.cache_disabled(env={"QUODEQ_DISABLE_ONLINE_CACHE": "0"})
    assert not online_cache.cache_disabled(env={})


def test_git_calls_carry_the_lfs_skip(tmp_path: Path, monkeypatch):
    seen: list[dict] = []

    def fake_run(_cmd, **kwargs):
        seen.append(kwargs["env"])
        raise OSError("no git")

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setenv("FROM_PROCESS", "1")
    assert online_cache._git(["status"]) is False
    assert seen[0]["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert seen[0]["FROM_PROCESS"] == "1"
