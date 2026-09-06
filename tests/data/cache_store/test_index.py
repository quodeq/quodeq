"""Content index: sqlite sidecar mapping (content hash, dimension, params) to keys.

Never authoritative and never fatal: a corrupt or missing db reports nothing
and is rebuilt by ensure_cache_ready. Lookups are verified against the entry
they point at before use (see analysis.cache._adoption).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.data.cache_store.index import INDEX_FILENAME, ContentIndex, IndexRow


@pytest.fixture
def index(tmp_path: Path) -> ContentIndex:
    return ContentIndex(tmp_path / INDEX_FILENAME)


def _rec(index: ContentIndex, key: str, *, path: str, created: str, hash_: str = "aa" * 32,
         dim: str = "security", params: str = "") -> None:
    index.record(key, content_hash=hash_, dimension=dim, params_hash=params,
                 file_path=path, created_at=created)


def test_record_then_find_newest_first(index: ContentIndex):
    _rec(index, "k1" * 32, path="ios/A.swift", created="2026-01-01T00:00:00+00:00")
    _rec(index, "k2" * 32, path="old/A.swift", created="2026-02-01T00:00:00+00:00")
    rows = index.find("aa" * 32, "security", "")
    assert rows == [
        IndexRow(key="k2" * 32, file_path="old/A.swift", created_at="2026-02-01T00:00:00+00:00"),
        IndexRow(key="k1" * 32, file_path="ios/A.swift", created_at="2026-01-01T00:00:00+00:00"),
    ]


def test_find_filters_on_dimension_and_params(index: ContentIndex):
    _rec(index, "k1" * 32, path="A.swift", created="t", dim="security", params="")
    _rec(index, "k2" * 32, path="A.swift", created="t", dim="reliability", params="")
    _rec(index, "k3" * 32, path="A.swift", created="t", dim="security", params="pp")
    assert [r.key for r in index.find("aa" * 32, "security", "")] == ["k1" * 32]
    assert [r.key for r in index.find("aa" * 32, "security", "pp")] == ["k3" * 32]


def test_find_respects_limit(index: ContentIndex):
    for i in range(5):
        _rec(index, f"k{i}" * 32, path=f"{i}/A.swift", created=f"2026-01-0{i + 1}")
    assert len(index.find("aa" * 32, "security", "", limit=2)) == 2


def test_forget_removes_row(index: ContentIndex):
    _rec(index, "k1" * 32, path="A.swift", created="t")
    index.forget("k1" * 32)
    assert index.find("aa" * 32, "security", "") == []


def test_record_replaces_existing_key(index: ContentIndex):
    _rec(index, "k1" * 32, path="A.swift", created="t1")
    _rec(index, "k1" * 32, path="B.swift", created="t2")
    rows = index.find("aa" * 32, "security", "")
    assert [(r.file_path, r.created_at) for r in rows] == [("B.swift", "t2")]


def test_empty_content_hash_is_never_recorded(index: ContentIndex):
    _rec(index, "k1" * 32, path="A.swift", created="t", hash_="")
    assert index.find("", "security", "") == []


def test_record_many_batches(index: ContentIndex):
    index.record_many([
        ("k1" * 32, "aa" * 32, "security", "", "A.swift", "t1"),
        ("k2" * 32, "aa" * 32, "security", "", "B.swift", "t2"),
        ("k3" * 32, "", "security", "", "C.swift", "t3"),  # blank hash skipped
    ])
    assert {r.key for r in index.find("aa" * 32, "security", "")} == {"k1" * 32, "k2" * 32}


def test_built_marker_round_trip(index: ContentIndex):
    assert index.built_for_schema() is None
    index.mark_built(4)
    assert index.built_for_schema() == 4


def test_corrupt_db_is_replaced_not_fatal(tmp_path: Path):
    db = tmp_path / INDEX_FILENAME
    db.write_text("this is not sqlite")
    index = ContentIndex(db)
    assert index.find("aa" * 32, "security", "") == []  # no raise
    _rec(index, "k1" * 32, path="A.swift", created="t")
    assert [r.key for r in index.find("aa" * 32, "security", "")] == ["k1" * 32]


def test_unwritable_location_degrades_silently(tmp_path: Path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    index = ContentIndex(blocker / INDEX_FILENAME)  # parent is a file: cannot create
    _rec(index, "k1" * 32, path="A.swift", created="t")
    assert index.find("aa" * 32, "security", "") == []
    assert index.built_for_schema() is None


def test_close_then_reuse_reopens(index: ContentIndex):
    _rec(index, "k1" * 32, path="A.swift", created="t")
    index.close()
    assert [r.key for r in index.find("aa" * 32, "security", "")] == ["k1" * 32]
