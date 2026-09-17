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

from quodeq.data.cache_store.key import SCHEMA_VERSION
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
