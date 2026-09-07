"""Schema 3 -> 4 migration, index build and legacy GC. One-time, lazy, lossless.

Entries store every key input, so a v3 entry (with language in its key) is
re-keyed to v4 (without language) from its own fields. The walk doubles as
the content-index build. Legacy (< 3) and unmigratable entries are reclaimed.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from quodeq.data.cache_store import migrate as mig
from quodeq.data.cache_store.entry import CacheEntry
from quodeq.data.cache_store.key import SCHEMA_VERSION, CacheKey, compute_key
from quodeq.data.cache_store.local import LocalFileBackend
from quodeq.data.cache_store.migrate import (
    MigrationStats,
    collect_legacy_entries,
    derive_params_hash,
    ensure_cache_ready,
    migrate_entries,
    ready_marker,
)

HASH = "aa" * 32


def _v3_key(path: str, dim: str, language: str, params_hash: str = "") -> str:
    """Reproduce the schema-3 formula (language in the canonical form)."""
    data = {
        "schema_version": 3, "file_content_hash": HASH, "file_path": path,
        "dimension": dim, "language": language,
    }
    if params_hash:
        data["params_hash"] = params_hash
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _write_raw(root: Path, key: str, payload: dict) -> Path:
    d = root / key[:2] / key[2:]
    d.mkdir(parents=True, exist_ok=True)
    (d / "entry.json").write_text(json.dumps(payload))
    return d


def _write_v3(root: Path, *, path: str, dim: str = "security", language: str = "typescript",
              effective: dict | None = None, consolidated: bool = True) -> str:
    key = _v3_key(path, dim, language)
    _write_raw(root, key, {
        "key": key, "schema_version": 3, "findings": [{"file": path, "line": 1}],
        "files_read": 1, "file_path": path, "dimension": dim, "model_id": "m",
        "file_content_hash": HASH, "language": language,
        "provenance": {"model_id": "m", "effective_params": effective or {}},
        "created_at": "2026-08-01T00:00:00+00:00", "cache_format_version": 2,
        "consolidated": consolidated,
    })
    return key


def _v4_key(path: str, dim: str = "security", params_hash: str = "") -> str:
    return compute_key(CacheKey(
        schema_version=SCHEMA_VERSION, file_content_hash=HASH, file_path=path,
        dimension=dim, params_hash=params_hash,
    ))


def _write_compiled(standards_dir: Path, dim: str, payload: dict) -> None:
    (standards_dir / "compiled").mkdir(parents=True, exist_ok=True)
    (standards_dir / "compiled" / f"{dim}.json").write_text(json.dumps(payload))


class TestDeriveParamsHash:
    _DIM = {"principles": [{"requirements": [
        {"id": "M-1", "params": {"max_lines": {"default": 50}}},
    ]}]}

    def test_blank_when_no_effective_params(self, tmp_path: Path):
        assert derive_params_hash("security", {}, tmp_path) == ""

    def test_blank_when_no_standards_dir(self):
        assert derive_params_hash("security", {"M-1": {"max_lines": 60}}, None) == ""

    def test_blank_when_compiled_missing(self, tmp_path: Path):
        assert derive_params_hash("security", {"M-1": {"max_lines": 60}}, tmp_path) == ""

    def test_blank_when_all_defaults(self, tmp_path: Path):
        _write_compiled(tmp_path, "security", self._DIM)
        assert derive_params_hash("security", {"M-1": {"max_lines": 50}}, tmp_path) == ""

    def test_matches_writer_formula_for_override(self, tmp_path: Path):
        from quodeq.core.standards.overrides import hash_non_default_params
        _write_compiled(tmp_path, "security", self._DIM)
        got = derive_params_hash("security", {"M-1": {"max_lines": 60}}, tmp_path)
        assert got == hash_non_default_params({"M-1": {"max_lines": 60}})

    def test_malformed_compiled_is_blank(self, tmp_path: Path):
        (tmp_path / "compiled").mkdir()
        (tmp_path / "compiled" / "security.json").write_text("{ nope")
        assert derive_params_hash("security", {"M-1": {"max_lines": 60}}, tmp_path) == ""


class TestMigrateEntries:
    def test_v3_entry_becomes_reachable_at_v4_key(self, tmp_path: Path):
        root = tmp_path / "cache"
        old_key = _write_v3(root, path="ios/A.swift")
        stats = migrate_entries(root, standards_dir=None)
        backend = LocalFileBackend(root=root)
        new = backend.get(_v4_key("ios/A.swift"))
        assert stats == MigrationStats(migrated=1, deduplicated=0, indexed=0, removed=0, skipped=0)
        assert new is not None
        assert new.schema_version == SCHEMA_VERSION
        assert new.key == _v4_key("ios/A.swift")
        assert new.language == "typescript"  # informational, kept
        assert new.params_hash == ""
        assert new.cache_format_version == 3
        assert new.consolidated is True
        assert new.findings == [{"file": "ios/A.swift", "line": 1}]
        assert not (root / old_key[:2] / old_key[2:]).exists()

    def test_entries_differing_only_in_language_collapse(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="A.kt", language="java")
        _write_v3(root, path="A.kt", language="kotlin")
        stats = migrate_entries(root, standards_dir=None)
        assert stats.migrated == 1 and stats.deduplicated == 1
        assert LocalFileBackend(root=root).get(_v4_key("A.kt")) is not None
        assert len(list(root.rglob("entry.json"))) == 1

    def test_migrated_entries_are_indexed(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="ios/A.swift")
        migrate_entries(root, standards_dir=None)
        rows = LocalFileBackend(root=root).find_by_content(HASH, "security", "")
        assert [r.file_path for r in rows] == ["ios/A.swift"]

    def test_existing_v4_entries_get_index_rows(self, tmp_path: Path):
        root = tmp_path / "cache"
        backend = LocalFileBackend(root=root)
        key = _v4_key("B.swift")
        backend.put(key, CacheEntry(
            key=key, schema_version=SCHEMA_VERSION, findings=[], files_read=1,
            file_path="B.swift", dimension="security", model_id="m", file_content_hash=HASH,
        ), index=False)
        stats = migrate_entries(root, standards_dir=None, backend=backend)
        assert stats.indexed == 1
        assert [r.key for r in backend.find_by_content(HASH, "security", "")] == [key]

    def test_params_hash_derived_from_effective_params(self, tmp_path: Path):
        from quodeq.core.standards.overrides import hash_non_default_params
        root = tmp_path / "cache"
        std = tmp_path / "standards"
        _write_compiled(std, "security", {"principles": [{"requirements": [
            {"id": "M-1", "params": {"max_lines": {"default": 50}}},
        ]}]})
        _write_v3(root, path="A.py", effective={"M-1": {"max_lines": 60}})
        migrate_entries(root, standards_dir=std)
        ph = hash_non_default_params({"M-1": {"max_lines": 60}})
        new = LocalFileBackend(root=root).get(_v4_key("A.py", params_hash=ph))
        assert new is not None and new.params_hash == ph

    def test_legacy_schema_2_entry_removed(self, tmp_path: Path):
        root = tmp_path / "cache"
        d = _write_raw(root, "cc" + "0" * 62, {
            "key": "cc" + "0" * 62, "schema_version": 2, "findings": [], "files_read": 1,
            "file_path": "a.py", "dimension": "security", "model_id": "m",
        })
        stats = migrate_entries(root, standards_dir=None)
        assert stats.removed == 1
        assert not d.exists()

    def test_unreadable_entry_left_in_place(self, tmp_path: Path):
        root = tmp_path / "cache"
        d = root / "dd" / ("1" * 62)
        d.mkdir(parents=True)
        (d / "entry.json").write_text("{ not json")
        stats = migrate_entries(root, standards_dir=None)
        assert stats.skipped == 1
        assert (d / "entry.json").exists()

    def test_second_pass_is_a_no_op(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="A.swift")
        migrate_entries(root, standards_dir=None)
        stats = migrate_entries(root, standards_dir=None)
        assert stats.migrated == 0 and stats.removed == 0
        assert stats.indexed == 1  # re-walk re-records the v4 row, harmless

    def test_missing_root_is_empty_stats(self, tmp_path: Path):
        assert migrate_entries(tmp_path / "nope", standards_dir=None) == MigrationStats()


class TestEnsureCacheReady:
    def setup_method(self):
        mig._ready_memo.clear()

    def test_migrates_marks_and_indexes(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="ios/A.swift")
        ensure_cache_ready(root, standards_dir=None)
        backend = LocalFileBackend(root=root)
        assert backend.get(_v4_key("ios/A.swift")) is not None
        assert ready_marker(root).exists()
        assert backend.index.built_for_schema() == SCHEMA_VERSION
        assert not (root / mig.LOCK_FILENAME).exists()

    def test_marker_short_circuits(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="first/A.swift")
        ensure_cache_ready(root, standards_dir=None)
        mig._ready_memo.clear()
        _write_v3(root, path="late/A.swift")  # seeded after the pass
        ensure_cache_ready(root, standards_dir=None)
        assert LocalFileBackend(root=root).get(_v4_key("late/A.swift")) is None

    def test_missing_index_is_rebuilt_even_with_marker(self, tmp_path: Path):
        from quodeq.data.cache_store.index import INDEX_FILENAME
        root = tmp_path / "cache"
        _write_v3(root, path="A.swift")
        ensure_cache_ready(root, standards_dir=None)
        for suffix in ("", "-wal", "-shm"):
            (root / (INDEX_FILENAME + suffix)).unlink(missing_ok=True)
        mig._ready_memo.clear()
        ensure_cache_ready(root, standards_dir=None)
        backend = LocalFileBackend(root=root)
        assert backend.index.built_for_schema() == SCHEMA_VERSION
        assert [r.file_path for r in backend.find_by_content(HASH, "security", "")] == ["A.swift"]

    def test_live_lock_skips_and_does_not_memo(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="A.swift")
        (root / mig.LOCK_FILENAME).write_text("12345")
        ensure_cache_ready(root, standards_dir=None)
        assert LocalFileBackend(root=root).get(_v4_key("A.swift")) is None
        assert not ready_marker(root).exists()
        # Lock released elsewhere: the next call (no memo) does the work.
        (root / mig.LOCK_FILENAME).unlink()
        ensure_cache_ready(root, standards_dir=None)
        assert LocalFileBackend(root=root).get(_v4_key("A.swift")) is not None

    def test_stale_lock_is_taken_over(self, tmp_path: Path):
        root = tmp_path / "cache"
        _write_v3(root, path="A.swift")
        lock = root / mig.LOCK_FILENAME
        lock.write_text("1")
        old = time.time() - mig.STALE_LOCK_S - 5
        os.utime(lock, (old, old))
        ensure_cache_ready(root, standards_dir=None)
        assert LocalFileBackend(root=root).get(_v4_key("A.swift")) is not None
        assert not lock.exists()

    def test_missing_root_is_a_no_op(self, tmp_path: Path):
        ensure_cache_ready(tmp_path / "nope", standards_dir=None)
        assert not (tmp_path / "nope").exists()


def test_collect_legacy_entries_still_available(tmp_path: Path):
    root = tmp_path / "cache"
    _write_raw(root, "aa" + "0" * 62, {"key": "aa" + "0" * 62, "schema_version": 2})
    _write_raw(root, "bb" + "1" * 62, {"key": "bb" + "1" * 62, "schema_version": 4})
    assert collect_legacy_entries(root, min_schema=4) == 1
    assert (root / "bb" / ("1" * 62) / "entry.json").exists()
