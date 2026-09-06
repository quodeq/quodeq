"""Cache maintenance shim: legacy GC plus the schema-4 migration entry point.

A key-formula change re-keys every entry, orphaning the old ones at paths
current lookups never reach. Entries older than the previous schema are dead
disk and are reclaimed; entries at the previous schema are self-describing
and are MIGRATED, never deleted. All of it runs once, lazily, on first cache
open, and must be best-effort: never fatal on a bad entry, a no-op on a
second pass, never touching current-schema entries.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.cache.gc import (
    collect_legacy_entries,
    ensure_cache_ready,
    maybe_collect_legacy_entries,
)


def _write_entry(root: Path, key: str, *, schema: int) -> Path:
    """Write a raw entry.json at the sharded path for *key*. Returns its dir."""
    entry_dir = root / key[:2] / key[2:]
    entry_dir.mkdir(parents=True, exist_ok=True)
    (entry_dir / "entry.json").write_text(json.dumps({
        "key": key, "schema_version": schema, "findings": [],
        "files_read": 1, "file_path": "a.py", "dimension": "security",
        "model_id": "m", "file_content_hash": "aa" * 32,
    }))
    return entry_dir


def test_collect_deletes_entries_below_min_schema(tmp_path: Path):
    root = tmp_path / "cache"
    old = _write_entry(root, "aa" + "0" * 62, schema=2)
    new = _write_entry(root, "bb" + "1" * 62, schema=4)

    removed = collect_legacy_entries(root, min_schema=4)

    assert removed == 1
    assert not (old / "entry.json").exists()
    assert (new / "entry.json").exists()


def test_collect_is_idempotent(tmp_path: Path):
    root = tmp_path / "cache"
    new = _write_entry(root, "bb" + "1" * 62, schema=4)
    _write_entry(root, "aa" + "0" * 62, schema=2)

    assert collect_legacy_entries(root, min_schema=4) == 1
    # Second pass finds nothing left to remove.
    assert collect_legacy_entries(root, min_schema=4) == 0
    assert (new / "entry.json").exists()


def test_collect_skips_unreadable_entry(tmp_path: Path):
    root = tmp_path / "cache"
    corrupt_dir = root / "cc" / ("2" * 62)
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "entry.json").write_text("{ not valid json")
    new = _write_entry(root, "bb" + "1" * 62, schema=4)

    # Must not raise; the corrupt entry is left in place (we can't read its
    # schema to know it's legacy), and current entries are untouched.
    removed = collect_legacy_entries(root, min_schema=4)

    assert removed == 0
    assert (corrupt_dir / "entry.json").exists()
    assert (new / "entry.json").exists()


def test_collect_handles_missing_root(tmp_path: Path):
    assert collect_legacy_entries(tmp_path / "does-not-exist", min_schema=4) == 0


def test_ensure_cache_ready_migrates_v3_instead_of_deleting(tmp_path: Path):
    from quodeq.data.cache_store import migrate as mig
    mig._ready_memo.clear()
    root = tmp_path / "cache"
    _write_entry(root, "aa" + "0" * 62, schema=2)   # legacy: reclaimed
    _write_entry(root, "bb" + "1" * 62, schema=3)   # migrate, never delete

    ensure_cache_ready(root)

    assert not (root / "aa" / ("0" * 62) / "entry.json").exists()
    assert not (root / "bb" / ("1" * 62) / "entry.json").exists()  # moved, not lost
    assert len(list(root.rglob("entry.json"))) == 1
    assert (root / ".schema_4_ready").exists()
    assert maybe_collect_legacy_entries is ensure_cache_ready

    # A legacy entry seeded after the one-time pass is NOT collected again.
    _write_entry(root, "dd" + "3" * 62, schema=2)
    ensure_cache_ready(root)
    assert (root / "dd" / ("3" * 62) / "entry.json").exists()
