"""A clean scan hashes each file once and invalidates the cache in one batch."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.cache.dimension_runner import CacheRunOptions, process_dimension_with_cache
from quodeq.analysis.fingerprint import hash_file
from quodeq.core.evidence.model import Evidence

from tests.analysis.cache._clean_scan_honor_fixtures import (
    _callbacks,
    _make_ctx,
    _setup_cache_with_hits,
)

_FILES = {"a.py": "x", "b.py": "y", "c.py": "z"}


class _CountingBackend(LocalFileBackend):
    def __init__(self, root: Path) -> None:
        super().__init__(root=root)
        self.single_deletes = 0
        self.batches: list[list[str]] = []

    def delete(self, key: str) -> None:
        self.single_deletes += 1
        super().delete(key)

    def delete_many(self, keys):
        batch = list(keys)
        self.batches.append(batch)
        return super().delete_many(batch)


def _run(tmp_path: Path, monkeypatch) -> tuple[_CountingBackend, list[int]]:
    cache = _CountingBackend(tmp_path / "cache_v2")
    config, _ = _setup_cache_with_hits(tmp_path, cache, _FILES, "security", sorted(_FILES))
    hashes: list[Path] = []

    def counting_hash(path):
        hashes.append(path)
        return hash_file(path)

    monkeypatch.setattr("quodeq.analysis.cache._key_provenance.hash_file", counting_hash)
    hashes_before_dispatch: list[int] = []

    def dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
        hashes_before_dispatch.append(len(hashes))
        return Evidence(repository="", language="python", date="2026-01-01",
                        source_file_count=0, files_read=0, coverage_pct=100.0, principles={})

    process_dimension_with_cache(
        config, "security", 1, _make_ctx(),
        opts=CacheRunOptions(callbacks=_callbacks(), cache=cache, dispatcher=dispatcher),
    )
    return cache, hashes_before_dispatch


def test_clean_scan_hashes_each_file_once_before_dispatch(tmp_path, monkeypatch):
    _, hashes_before_dispatch = _run(tmp_path, monkeypatch)
    assert hashes_before_dispatch == [len(_FILES)]


def test_clean_scan_invalidates_with_one_batched_delete(tmp_path, monkeypatch):
    cache, _ = _run(tmp_path, monkeypatch)
    assert cache.single_deletes == 0
    assert len(cache.batches) == 1
    assert len(cache.batches[0]) == len(_FILES)
