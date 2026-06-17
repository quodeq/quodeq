"""Local filesystem backend — atomic writes, sharding, corruption handling."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.local import LocalFileBackend, default_cache_root


def _make_entry(key: str = "k" * 64) -> CacheEntry:
    return CacheEntry(
        key=key, schema_version=1, findings=[{"file": "a.py", "line": 1}],
        files_read=1, file_path="a.py", dimension="security",
        model_id="claude-opus-4-7",
    )


@pytest.fixture
def backend(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


class TestRoundTrip:
    def test_put_then_get(self, backend: LocalFileBackend):
        entry = _make_entry()
        backend.put(entry.key, entry)
        loaded = backend.get(entry.key)
        assert loaded is not None
        assert loaded.key == entry.key
        assert loaded.findings == entry.findings

    def test_miss_returns_none(self, backend: LocalFileBackend):
        assert backend.get("0" * 64) is None

    def test_has_reflects_state(self, backend: LocalFileBackend):
        entry = _make_entry()
        assert backend.has(entry.key) is False
        backend.put(entry.key, entry)
        assert backend.has(entry.key) is True
        backend.delete(entry.key)
        assert backend.has(entry.key) is False


class TestSharding:
    def test_uses_two_char_prefix(self, backend: LocalFileBackend, tmp_path: Path):
        key = "abcdef" + "0" * 58
        backend.put(key, _make_entry(key))
        expected = tmp_path / "cache" / "ab" / ("cdef" + "0" * 58) / "entry.json"
        assert expected.is_file()

    def test_short_key_rejected(self, backend: LocalFileBackend):
        with pytest.raises(ValueError):
            backend.has("ab")

    def test_traversal_key_rejected(self, backend: LocalFileBackend):
        for bad in ["../../etc/passwd", "ab/cd", "abc.def", "/abcdef"]:
            with pytest.raises(ValueError):
                backend.has(bad)


class TestAtomicity:
    def test_put_overwrites_atomically(self, backend: LocalFileBackend):
        # Two successive puts: reader always sees a complete entry, never partial.
        entry_v1 = _make_entry()
        backend.put(entry_v1.key, entry_v1)
        entry_v2 = CacheEntry(
            key=entry_v1.key, schema_version=1, findings=[{"new": True}],
            files_read=2, file_path="a.py", dimension="security",
            model_id="claude-opus-4-7",
        )
        backend.put(entry_v2.key, entry_v2)
        loaded = backend.get(entry_v1.key)
        assert loaded is not None
        assert loaded.findings == [{"new": True}]
        assert loaded.files_read == 2

    def test_orphan_tmp_file_does_not_block_reader(self, backend: LocalFileBackend, tmp_path: Path):
        entry = _make_entry()
        backend.put(entry.key, entry)
        # Simulate a crashed concurrent writer: an orphan .tmp.* file in the
        # same directory must not affect readers of the committed entry.
        target_dir = tmp_path / "cache" / entry.key[:2] / entry.key[2:]
        (target_dir / ".tmp.99999.deadbeef").write_text("partial garbage")
        loaded = backend.get(entry.key)
        assert loaded is not None
        assert loaded.findings == entry.findings


class TestCorruption:
    def test_corrupt_entry_treated_as_miss_and_removed(self, backend: LocalFileBackend, tmp_path: Path):
        key = "ff" * 32
        target_dir = tmp_path / "cache" / key[:2] / key[2:]
        target_dir.mkdir(parents=True)
        (target_dir / "entry.json").write_text("{not valid json")
        # Get returns None and deletes the corrupt file so the next put can heal.
        assert backend.get(key) is None
        assert not (target_dir / "entry.json").exists()

    def test_missing_root_returns_none(self, tmp_path: Path):
        backend = LocalFileBackend(root=tmp_path / "does-not-exist")
        assert backend.get("a" * 64) is None
        assert backend.has("a" * 64) is False


class TestStats:
    def test_empty_root_zero_stats(self, backend: LocalFileBackend):
        s = backend.stats()
        assert s.entries == 0
        assert s.bytes == 0

    def test_counts_entries_and_bytes(self, backend: LocalFileBackend):
        keys = [f"{i:064x}" for i in range(3)]
        for k in keys:
            backend.put(k, _make_entry(k))
        s = backend.stats()
        assert s.entries == 3
        assert s.bytes > 0


class TestCacheRoot:
    def test_default_under_quodeq_cache(self, monkeypatch):
        monkeypatch.delenv("QUODEQ_CACHE_ROOT", raising=False)
        root = default_cache_root()
        assert root.name == "results"
        assert root.parent.name == "cache"
        assert root.parent.parent.name == ".quodeq"

    def test_root_env_override(self, monkeypatch, tmp_path: Path):
        override = tmp_path / "sandboxed"
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(override))
        root = default_cache_root()
        assert root == override / "results"

    def test_root_ignored_when_blank(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_CACHE_ROOT", "   ")
        root = default_cache_root()
        assert ".quodeq" in root.parts
