"""LocalFileBackend.stats() memo.

The walk behind stats() stat()s every entry file (100k possible), so repeated
calls inside the TTL must not redo it. A put, delete or corrupt-entry removal
through the same instance must show up at once; a change made behind the
backend's back (another process) shows up once the memo expires.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.data.cache_store import local
from quodeq.data.cache_store.entry import CacheEntry
from quodeq.data.cache_store.local import LocalFileBackend


def _entry(key: str) -> CacheEntry:
    return CacheEntry(
        key=key, schema_version=4, findings=[], files_read=1, file_path="a.py",
        dimension="security", model_id="m", file_content_hash="aa" * 32,
    )


def _write_raw(root: Path, key: str, text: str = "{}") -> Path:
    """Drop an entry file on disk without going through the backend."""
    d = root / key[:2] / key[2:]
    d.mkdir(parents=True, exist_ok=True)
    path = d / "entry.json"
    path.write_text(text)
    return path


@pytest.fixture
def clock(monkeypatch) -> list[float]:
    """Fake monotonic clock for ``local`` only; ``clock[0] += n`` advances it."""
    now = [1000.0]
    monkeypatch.setattr(local, "time", SimpleNamespace(monotonic=lambda: now[0]))
    return now


@pytest.fixture
def backend(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache", enable_index=False)


def test_repeat_calls_reuse_the_walk_until_ttl(backend: LocalFileBackend, clock: list[float]):
    backend.put("k1" * 32, _entry("k1" * 32))
    assert backend.stats().entries == 1
    _write_raw(backend.root, "k2" * 32)  # behind the backend's back
    assert backend.stats().entries == 1, "memo must hold inside the TTL"
    clock[0] += local._STATS_TTL_S
    assert backend.stats().entries == 2


def test_put_and_delete_refresh_at_once(backend: LocalFileBackend, clock: list[float]):
    assert backend.stats() == local.CacheStats(entries=0, bytes=0)
    backend.put("k1" * 32, _entry("k1" * 32))
    on_disk = (backend.root / "k1" / ("k1" * 31) / "entry.json").stat().st_size
    assert backend.stats() == local.CacheStats(entries=1, bytes=on_disk)
    backend.put("k2" * 32, _entry("k2" * 32))
    assert backend.stats().entries == 2
    backend.delete("k1" * 32)
    assert backend.stats() == local.CacheStats(entries=1, bytes=on_disk)


def test_corrupt_entry_removal_refreshes_at_once(backend: LocalFileBackend, clock: list[float]):
    _write_raw(backend.root, "ff" * 32, "{not json")
    assert backend.stats().entries == 1
    assert backend.get("ff" * 32) is None  # unlinks the corrupt file
    assert backend.stats().entries == 0


def test_failed_delete_keeps_the_memo(backend: LocalFileBackend, clock: list[float], monkeypatch):
    backend.put("k1" * 32, _entry("k1" * 32))
    assert backend.stats().entries == 1
    _write_raw(backend.root, "k2" * 32)
    monkeypatch.setattr(local.shutil, "rmtree", _raise_oserror)
    backend.delete("k1" * 32)  # logs and returns; nothing changed on disk
    assert backend.stats().entries == 1


def test_missing_root_is_memoised_too(tmp_path: Path, clock: list[float]):
    backend = LocalFileBackend(root=tmp_path / "absent", enable_index=False)
    assert backend.stats() == local.CacheStats(entries=0, bytes=0)
    _write_raw(backend.root, "k1" * 32)
    assert backend.stats().entries == 0
    clock[0] += local._STATS_TTL_S
    assert backend.stats().entries == 1


def test_returned_stats_is_not_the_memo(backend: LocalFileBackend, clock: list[float]):
    backend.put("k1" * 32, _entry("k1" * 32))
    first = backend.stats()
    first.entries = 99
    assert backend.stats().entries == 1


def _raise_oserror(*_args, **_kwargs) -> None:
    raise OSError("simulated rmtree failure")
