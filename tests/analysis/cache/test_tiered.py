"""TieredCache — local-first with optional remote fallback."""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis.cache.backend import CacheStats
from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.cache.tiered import TieredCache


class _SpyBackend:
    """In-memory backend with optional failure injection."""

    def __init__(self, *, fail: bool = False) -> None:
        self.store: dict[str, CacheEntry] = {}
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def _check(self, op: str, key: str) -> None:
        self.calls.append((op, key))
        if self.fail:
            raise RuntimeError(f"injected {op} failure")

    def get(self, key: str) -> CacheEntry | None:
        self._check("get", key)
        return self.store.get(key)

    def put(self, key: str, entry: CacheEntry) -> None:
        self._check("put", key)
        self.store[key] = entry

    def has(self, key: str) -> bool:
        self._check("has", key)
        return key in self.store

    def delete(self, key: str) -> None:
        self._check("delete", key)
        self.store.pop(key, None)

    def stats(self) -> CacheStats:
        return CacheStats(entries=len(self.store), bytes=0)


def _entry(key: str) -> CacheEntry:
    return CacheEntry(
        key=key, schema_version=1, findings=[{"file": "a.py"}],
        files_read=1, file_path="a.py", dimension="security",
        model_id="claude-opus-4-7",
    )


@pytest.fixture
def local(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


class TestLocalOnly:
    def test_local_hit(self, local: LocalFileBackend):
        cache = TieredCache(local=local)
        e = _entry("a" * 64)
        cache.put(e.key, e)
        assert cache.get(e.key) is not None

    def test_local_miss_no_remote(self, local: LocalFileBackend):
        cache = TieredCache(local=local)
        assert cache.get("0" * 64) is None


class TestRemoteFallback:
    def test_remote_hit_warms_local(self, local: LocalFileBackend):
        remote = _SpyBackend()
        e = _entry("b" * 64)
        remote.store[e.key] = e
        cache = TieredCache(local=local, remote=remote)
        # First read: local miss, remote hit, local now warmed.
        loaded = cache.get(e.key)
        assert loaded is not None
        assert local.has(e.key)
        # Second read: local hit, remote untouched.
        remote.calls.clear()
        cache.get(e.key)
        assert remote.calls == []

    def test_put_writes_both_tiers(self, local: LocalFileBackend):
        remote = _SpyBackend()
        cache = TieredCache(local=local, remote=remote)
        e = _entry("c" * 64)
        cache.put(e.key, e)
        assert local.has(e.key)
        assert e.key in remote.store


class TestRemoteFailureIsolation:
    def test_remote_get_failure_does_not_propagate(self, local: LocalFileBackend):
        remote = _SpyBackend(fail=True)
        cache = TieredCache(local=local, remote=remote)
        # Local miss + remote raise → returns None, no exception.
        assert cache.get("0" * 64) is None

    def test_remote_put_failure_does_not_propagate(self, local: LocalFileBackend):
        remote = _SpyBackend(fail=True)
        cache = TieredCache(local=local, remote=remote)
        e = _entry("d" * 64)
        cache.put(e.key, e)  # must not raise
        # Local write still succeeded.
        assert local.has(e.key)

    def test_remote_has_failure_returns_false(self, local: LocalFileBackend):
        remote = _SpyBackend(fail=True)
        cache = TieredCache(local=local, remote=remote)
        assert cache.has("0" * 64) is False
