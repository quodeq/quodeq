import os
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.context import online_cache


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    """Point QUODEQ_CACHE_ROOT at a tmpdir for every test in this module."""
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.delenv("QUODEQ_DISABLE_ONLINE_CACHE", raising=False)
    yield


def test_cache_root_creates_online_subdir(tmp_path):
    root = online_cache.cache_root()
    assert root.exists()
    assert root.name == "online"
    assert root.parent == tmp_path / "cache"


def test_cache_dir_for_url_is_deterministic():
    a = online_cache.cache_dir_for_url("https://github.com/quodeq/quodeq")
    b = online_cache.cache_dir_for_url("https://github.com/quodeq/quodeq")
    assert a == b


def test_cache_dir_for_url_separates_distinct_urls():
    a = online_cache.cache_dir_for_url("https://github.com/owner/a")
    b = online_cache.cache_dir_for_url("https://github.com/owner/b")
    assert a != b


def test_cache_dir_normalizes_whitespace_around_url():
    a = online_cache.cache_dir_for_url("https://github.com/x/y")
    b = online_cache.cache_dir_for_url("  https://github.com/x/y  ")
    assert a == b


def test_repo_path_for_url_is_under_cache_dir():
    repo = online_cache.repo_path_for_url("https://github.com/x/y")
    assert repo.name == "repo"
    assert repo.parent == online_cache.cache_dir_for_url("https://github.com/x/y")


def test_is_inside_cache_recognizes_cache_paths():
    cached = online_cache.repo_path_for_url("https://github.com/x/y")
    cached.mkdir(parents=True)
    assert online_cache.is_inside_cache(cached) is True


def test_is_inside_cache_rejects_external_paths(tmp_path):
    external = tmp_path / "elsewhere"
    external.mkdir()
    assert online_cache.is_inside_cache(external) is False


def test_cache_disabled_reads_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "1")
    assert online_cache.cache_disabled() is True
    monkeypatch.setenv("QUODEQ_DISABLE_ONLINE_CACHE", "")
    assert online_cache.cache_disabled() is False


def test_ensure_clone_first_time_calls_git_clone():
    url = "https://github.com/x/y"

    def fake_git(args, *, cwd=None, timeout=300):
        if args and args[0] == "clone":
            # Simulate a successful clone by creating the .git marker.
            dest = Path(args[-1])
            (dest / ".git").mkdir(parents=True)
            return True
        return True

    with patch.object(online_cache, "_git", side_effect=fake_git) as mock_git:
        repo = online_cache.ensure_clone(url)
    assert repo is not None
    assert (repo / ".git").exists()
    # First call: clone. No fetch / reset on a fresh clone.
    clone_calls = [c for c in mock_git.call_args_list if c.args[0][0] == "clone"]
    assert len(clone_calls) == 1


def test_ensure_clone_existing_calls_fetch_and_reset(tmp_path):
    url = "https://github.com/x/y"
    repo = online_cache.repo_path_for_url(url)
    (repo / ".git").mkdir(parents=True)

    with patch.object(online_cache, "_git", return_value=True) as mock_git:
        result = online_cache.ensure_clone(url)
    assert result == repo
    arg_lists = [c.args[0] for c in mock_git.call_args_list]
    assert ["fetch", "--depth", "1", "origin", "HEAD"] in arg_lists
    assert ["reset", "--hard", "FETCH_HEAD"] in arg_lists
    # No clone — already present.
    assert not any(args[0] == "clone" for args in arg_lists)


def test_ensure_clone_returns_none_when_initial_clone_fails():
    url = "https://github.com/missing/repo"
    with patch.object(online_cache, "_git", return_value=False):
        assert online_cache.ensure_clone(url) is None
    # Ensure no half-clone left behind.
    assert not online_cache.repo_path_for_url(url).exists()


def test_ensure_clone_returns_existing_path_even_if_refresh_fails(tmp_path):
    """A flaky network shouldn't take out evals against an already-cached repo."""
    url = "https://github.com/x/y"
    repo = online_cache.repo_path_for_url(url)
    (repo / ".git").mkdir(parents=True)
    with patch.object(online_cache, "_git", return_value=False):
        assert online_cache.ensure_clone(url) == repo


def test_wipe_cache_removes_all_entries():
    online_cache.repo_path_for_url("https://x/a").mkdir(parents=True)
    online_cache.repo_path_for_url("https://x/b").mkdir(parents=True)
    assert len(list(online_cache.cache_root().iterdir())) == 2
    wiped = online_cache.wipe_cache()
    assert wiped == 2
    assert list(online_cache.cache_root().iterdir()) == []
    # Cache root itself still exists.
    assert online_cache.cache_root().exists()


def test_ensure_clone_evicts_oldest_entries_beyond_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(online_cache, "_MAX_CACHED_REPOS", 2)

    def fake_git(args, *, cwd=None, timeout=300):
        if args[0] == "clone":
            dest = Path(args[-1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir()
            return True
        return True  # fetch/reset no-ops on an already-cloned repo

    with patch.object(online_cache, "_git", side_effect=fake_git):
        online_cache.ensure_clone("https://example.com/a.git")
        online_cache.ensure_clone("https://example.com/b.git")
        online_cache.ensure_clone("https://example.com/c.git")  # 3rd entry, cap is 2

    entries = [e for e in online_cache.cache_root().iterdir() if e.is_dir()]
    assert len(entries) == 2, "cache must be pruned to _MAX_CACHED_REPOS entries"
    # The most recently cloned ("c") must survive.
    c_dir = online_cache.cache_dir_for_url("https://example.com/c.git")
    assert c_dir in entries


def test_ensure_clone_evicts_least_recently_used_not_least_recently_cloned(tmp_path, monkeypatch):
    """Eviction order must track actual use, not just clone order.

    Regression test for the LRU defect: a cache entry's own directory mtime
    never changes just because its repo/ subdirectory gets fetched+reset
    (git's writes land deeper inside, under repo/.git), so relying on that
    incidental side effect makes pruning evict "oldest-ever-cloned" forever,
    even for entries used every single run. Eviction must instead be driven
    by an explicit _touch() on every use.
    """
    monkeypatch.setattr(online_cache, "_MAX_CACHED_REPOS", 3)

    def fake_git(args, *, cwd=None, timeout=300):
        if args[0] == "clone":
            dest = Path(args[-1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / ".git").mkdir()
            return True
        return True  # fetch/reset no-ops — deliberately touch nothing themselves

    urls = {name: f"https://example.com/{name}.git" for name in "abc"}
    dirs = {name: online_cache.cache_dir_for_url(url) for name, url in urls.items()}

    with patch.object(online_cache, "_git", side_effect=fake_git):
        for name in "abc":
            online_cache.ensure_clone(urls[name])

    # Pin a deterministic clone-order mtime spread (A oldest, C newest) so
    # the test doesn't depend on how fast three back-to-back clones run.
    base = 1_000_000
    for i, name in enumerate("abc"):
        os.utime(dirs[name], (base + i, base + i))

    # "Use" A again, well after B and C were touched above — this is the
    # signal that must save A from eviction despite being cloned first.
    online_cache._touch(dirs["a"])

    # A 4th clone pushes the cache over the cap, forcing one eviction.
    with patch.object(online_cache, "_git", side_effect=fake_git):
        online_cache.ensure_clone("https://example.com/d.git")

    entries = {e.name for e in online_cache.cache_root().iterdir() if e.is_dir()}
    d_dir = online_cache.cache_dir_for_url("https://example.com/d.git")
    assert entries == {dirs["a"].name, dirs["c"].name, d_dir.name}, (
        "A (re-used) and D (just-cloned) must survive; "
        "B (neither re-used nor most-recent) must be evicted over A despite "
        "having been cloned before A"
    )
