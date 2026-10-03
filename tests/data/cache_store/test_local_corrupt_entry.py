"""A non-UTF-8 cache entry reads as a miss and is removed, like a corrupt one."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.cache_store.entry import CacheEntry
from quodeq.data.cache_store.local import LocalFileBackend

_KEY = "ab" * 32


def test_non_utf8_entry_is_a_miss_and_is_removed(tmp_path: Path) -> None:
    backend = LocalFileBackend(root=tmp_path, enable_index=False)
    backend.put(_KEY, CacheEntry(key=_KEY, schema_version=1, findings=[], files_read=1,
                                 file_path="a.py", dimension="security", model_id="m",
                                 file_content_hash="h-a"))
    [entry_file] = [p for p in tmp_path.rglob("*") if p.is_file()]
    entry_file.write_bytes(b"\xff\xfe not utf-8")
    assert backend.get(_KEY) is None
    assert not entry_file.exists()
