"""LocalFileBackend.delete_many and ContentIndex.forget_many."""
from __future__ import annotations

import gc
import shutil
import sqlite3
from pathlib import Path

import pytest

from quodeq.data.cache_store.entry import CacheEntry
from quodeq.data.cache_store.index import ContentIndex, IndexEntry
from quodeq.data.cache_store.local import LocalFileBackend


def _entry(key: str) -> CacheEntry:
    return CacheEntry(key=key, schema_version=1, findings=[], files_read=1,
                      file_path=f"{key[:4]}.py", dimension="security", model_id="m",
                      file_content_hash=f"h-{key[:4]}")


def _keys(n: int) -> list[str]:
    return [f"{i:02d}" + "a" * 62 for i in range(n)]


class _CountingIndex(ContentIndex):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.forget_calls: list[list[str]] = []

    def forget_many(self, keys):
        batch = list(keys)
        self.forget_calls.append(batch)
        super().forget_many(batch)


def _backend(tmp_path: Path) -> tuple[LocalFileBackend, _CountingIndex]:
    index = _CountingIndex(tmp_path / ".index.db")
    return LocalFileBackend(root=tmp_path, index=index), index


def test_delete_many_removes_every_entry_and_forgets_rows_in_one_call(tmp_path):
    backend, index = _backend(tmp_path)
    keys = _keys(5)
    for key in keys:
        backend.put(key, _entry(key))

    removed = backend.delete_many(keys)

    assert removed == 5
    assert not any(backend.has(key) for key in keys)
    assert index.forget_calls == [keys]
    assert backend.find_by_content("h-00aa", "security", "") == []


def test_delete_many_skips_missing_and_invalid_keys(tmp_path):
    backend, index = _backend(tmp_path)
    keys = _keys(2)
    backend.put(keys[0], _entry(keys[0]))

    removed = backend.delete_many([keys[0], keys[1], "../escape"])

    assert removed == 1
    assert index.forget_calls == [[keys[0]]]


def test_delete_many_keeps_the_index_row_of_an_entry_it_could_not_remove(tmp_path, monkeypatch):
    backend, index = _backend(tmp_path)
    keys = _keys(2)
    for key in keys:
        backend.put(key, _entry(key))
    real_rmtree = shutil.rmtree
    stuck = backend._dir_for(keys[0])

    def flaky(path, *a, **k):
        if Path(path) == stuck:
            raise PermissionError("locked")
        real_rmtree(path, *a, **k)

    monkeypatch.setattr("quodeq.data.cache_store.local.shutil.rmtree", flaky)

    assert backend.delete_many(keys) == 1
    assert backend.has(keys[0])
    assert index.forget_calls == [[keys[1]]]


def test_delete_many_with_nothing_removed_opens_no_index_transaction(tmp_path):
    backend, index = _backend(tmp_path)
    assert backend.delete_many(_keys(3)) == 0
    assert index.forget_calls == []


def test_a_dropped_index_closes_its_connection(tmp_path):
    index = ContentIndex(tmp_path / ".index.db")
    index.record(IndexEntry(key="k" * 64, content_hash="h", dimension="d",
                            params_hash="", file_path="a.py", created_at=""))
    conn = index._conn
    assert conn is not None
    del index
    gc.collect()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
