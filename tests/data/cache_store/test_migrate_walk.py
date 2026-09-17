"""migrate_entries walks root.rglob(entry.json) lazily.

Sibling of test_migrate.py (already at the 240-line test-file cap). Covers
one thing: reclaiming an entry mid-walk (its directory removed) must not
truncate the walk before it reaches the entries that come after it. Safe
because every reclaimed directory is a leaf (one entry.json, no
subdirectories -- see local.py's two-char sharding) that the walk has
already listed by the time it is removed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.data.cache_store.key import SCHEMA_VERSION, CacheKey, compute_key
from quodeq.data.cache_store.local import LocalFileBackend
from quodeq.data.cache_store.migrate import migrate_entries


def _write_raw(root: Path, key: str, payload: dict) -> Path:
    d = root / key[:2] / key[2:]
    d.mkdir(parents=True, exist_ok=True)
    (d / "entry.json").write_text(json.dumps(payload))
    return d


def _v4_payload(key: str, file_path: str) -> dict:
    return {
        "key": key, "schema_version": SCHEMA_VERSION, "findings": [],
        "files_read": 1, "file_path": file_path, "dimension": "security",
        "model_id": "m", "file_content_hash": "b" * 64,
    }


def test_reclaiming_one_entry_mid_walk_still_visits_the_others(tmp_path: Path):
    root = tmp_path / "cache"
    # A legacy (schema 2) entry: reclaimed, its directory removed as the walk visits it.
    _write_raw(root, "aa" + "0" * 62, {
        "key": "aa" + "0" * 62, "schema_version": 2, "findings": [],
        "files_read": 1, "file_path": "a.py", "dimension": "security", "model_id": "m",
    })
    # Two current-schema entries that must still be seen and indexed, whichever
    # side of the reclaimed one they land on in the directory listing.
    _write_raw(root, "bb" + "1" * 62, _v4_payload("bb" + "1" * 62, "b.py"))
    _write_raw(root, "cc" + "2" * 62, _v4_payload("cc" + "2" * 62, "c.py"))

    stats = migrate_entries(root, standards_dir=None)

    assert stats.removed == 1
    assert stats.indexed == 2
    assert not (root / "aa" / ("0" * 62)).exists()
    assert (root / "bb" / ("1" * 62) / "entry.json").exists()
    assert (root / "cc" / ("2" * 62) / "entry.json").exists()


# --- An entry the walk itself writes must not be counted again -------------
# _migrate_v3 puts the re-keyed entry under a new shard. When that shard is
# a directory the lazy walk has not reached yet, rglob yields the new
# entry.json too and the migrated entry is indexed a second time.

_DIM = "security"


def _v3_payload(key: str, file_path: str, content_hash: str) -> dict:
    return {
        "key": key, "schema_version": SCHEMA_VERSION - 1, "findings": [],
        "files_read": 1, "file_path": file_path, "dimension": _DIM,
        "model_id": "m", "file_content_hash": content_hash,
    }


def _seed_v3(root: Path, file_path: str, content_hash: str, old_shard: str) -> str:
    """Write one v3 entry under *old_shard*, and return its migrated key.

    The old key shares the migrated key's tail so the two differ only in the
    shard the entry lives in, which is what decides whether the walk reaches
    the migrated copy after writing it.
    """
    new_key = compute_key(CacheKey(
        schema_version=SCHEMA_VERSION, file_content_hash=content_hash,
        file_path=file_path, dimension=_DIM, params_hash="",
    ))
    assert not new_key.startswith(old_shard), "pick a shard the migration won't reuse"
    old_key = old_shard + new_key[2:]
    _write_raw(root, old_key, _v3_payload(old_key, file_path, content_hash))
    # The destination shard already exists in a real cache, so the walk's own
    # listing of root includes it and it gets scanned after the old shard.
    (root / new_key[:2]).mkdir(parents=True, exist_ok=True)
    return new_key


@pytest.mark.parametrize("old_shard", ["00", "ff"])
def test_entries_written_during_the_walk_are_not_counted_twice(
    tmp_path: Path, old_shard: str,
) -> None:
    root = tmp_path / "cache"
    files = {"a.py": "a" * 64, "b.py": "b" * 64, "c.py": "c" * 64}
    new_keys = [
        _seed_v3(root, name, content_hash, old_shard)
        for name, content_hash in files.items()
    ]

    stats = migrate_entries(root, standards_dir=None)

    assert stats.migrated + stats.indexed == len(files)
    assert stats.indexed == 0, "a migrated entry was re-read as a v4 entry"
    assert stats.deduplicated == 0
    index = LocalFileBackend(root=root).index
    assert index is not None
    rows = [index.find(h, _DIM, "") for h in files.values()]
    assert [len(r) for r in rows] == [1, 1, 1]
    assert {r[0].key for r in rows} == set(new_keys)
    index.close()
