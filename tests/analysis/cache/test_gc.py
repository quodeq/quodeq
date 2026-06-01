"""One-time GC of cache entries from an older schema.

The permissive-key change (schema 2 -> 3) re-keys every entry, orphaning the
old ones at paths current lookups never reach. The GC reclaims that dead disk
once, lazily, on first cache open under the new schema. It must be
best-effort and idempotent: never fatal on a bad entry, a no-op on a second
pass, and it must never touch current-schema entries.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.cache.gc import (
    collect_legacy_entries,
    maybe_collect_legacy_entries,
)


def _write_entry(root: Path, key: str, *, schema: int) -> Path:
    """Write a raw entry.json at the sharded path for *key*. Returns its dir."""
    entry_dir = root / key[:2] / key[2:]
    entry_dir.mkdir(parents=True, exist_ok=True)
    (entry_dir / "entry.json").write_text(json.dumps({
        "key": key, "schema_version": schema, "findings": [],
        "files_read": 1, "file_path": "a.py", "dimension": "security",
        "model_id": "m",
    }))
    return entry_dir


def test_collect_deletes_entries_below_min_schema(tmp_path: Path):
    root = tmp_path / "cache"
    old = _write_entry(root, "aa" + "0" * 62, schema=2)
    new = _write_entry(root, "bb" + "1" * 62, schema=3)

    removed = collect_legacy_entries(root, min_schema=3)

    assert removed == 1
    assert not (old / "entry.json").exists()
    assert (new / "entry.json").exists()


def test_collect_is_idempotent(tmp_path: Path):
    root = tmp_path / "cache"
    new = _write_entry(root, "bb" + "1" * 62, schema=3)
    _write_entry(root, "aa" + "0" * 62, schema=2)

    assert collect_legacy_entries(root, min_schema=3) == 1
    # Second pass finds nothing left to remove.
    assert collect_legacy_entries(root, min_schema=3) == 0
    assert (new / "entry.json").exists()


def test_collect_skips_unreadable_entry(tmp_path: Path):
    root = tmp_path / "cache"
    corrupt_dir = root / "cc" / ("2" * 62)
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "entry.json").write_text("{ not valid json")
    new = _write_entry(root, "bb" + "1" * 62, schema=3)

    # Must not raise; the corrupt entry is left in place (we can't read its
    # schema to know it's legacy), and current entries are untouched.
    removed = collect_legacy_entries(root, min_schema=3)

    assert removed == 0
    assert (corrupt_dir / "entry.json").exists()
    assert (new / "entry.json").exists()


def test_collect_handles_missing_root(tmp_path: Path):
    assert collect_legacy_entries(tmp_path / "does-not-exist", min_schema=3) == 0


def test_maybe_collect_runs_once_per_process(tmp_path: Path):
    root = tmp_path / "cache"
    _write_entry(root, "aa" + "0" * 62, schema=2)

    maybe_collect_legacy_entries(root)
    assert not (root / "aa" / ("0" * 62) / "entry.json").exists()  # collected
    assert (root / ".gc_schema_3").exists()  # marker written

    # A legacy entry seeded after the one-time pass is NOT collected again.
    _write_entry(root, "dd" + "3" * 62, schema=2)
    maybe_collect_legacy_entries(root)
    assert (root / "dd" / ("3" * 62) / "entry.json").exists()
