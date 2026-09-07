"""Adoption: a classify miss reuses an entry with the same content hash when
the file merely moved (same basename, same path role). This is what makes a
directory restructure (freemium-app-ios moved ios/ to the repo root) cost
zero re-evaluation for unchanged files."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import CacheEntry, LocalFileBackend
from quodeq.analysis.cache._key_provenance import build_cache_key_struct
from quodeq.analysis.cache.dimension_helpers import (
    build_cache_key_for_file,
    classify_files_via_cache,
)
from quodeq.analysis.cache.key import compute_key


def _config(src: Path, language: str = "swift") -> RunConfig:
    return RunConfig(
        src=src, language=language, standards_dir=None, work_dir=src,
        options=AnalysisOptions(subagent_model="test-model"),
    )


def _seed_old(cache: LocalFileBackend, src: Path, old_path: str, new_path: str,
              *, dim: str = "security", consolidated: bool = True,
              findings: list[dict] | None = None) -> str:
    """Seed an entry for *old_path* whose content equals the file now at *new_path*."""
    struct = build_cache_key_struct(_config(src), new_path, dim)
    old_key = compute_key(replace(struct, file_path=old_path))
    cache.put(old_key, CacheEntry(
        key=old_key, schema_version=struct.schema_version,
        findings=findings if findings is not None else [{"file": old_path, "line": 3, "t": "violation"}],
        files_read=1, file_path=old_path, dimension=dim, model_id="test-model",
        file_content_hash=struct.file_content_hash, language="typescript",
        provenance={"model_id": "test-model"}, consolidated=consolidated,
    ))
    return old_key


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


def _write(src: Path, rel: str, text: str = "class Foo {}") -> None:
    p = src / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_directory_move_adopts_and_rewrites_file_field(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "KubusApp/Foo.swift")
    _seed_old(cache, src, "ios/KubusApp/Foo.swift", "KubusApp/Foo.swift")

    result = classify_files_via_cache(_config(src), "security", ["KubusApp/Foo.swift"], cache)

    assert result.misses == []
    assert result.adopted == 1
    assert result.cached_findings == [{"file": "KubusApp/Foo.swift", "line": 3, "t": "violation"}]
    new_key = build_cache_key_for_file(_config(src), "KubusApp/Foo.swift", "security")
    adopted = cache.get(new_key)
    assert adopted is not None
    assert adopted.file_path == "KubusApp/Foo.swift"
    assert adopted.language == "swift"
    assert adopted.provenance["adopted_from"] == "ios/KubusApp/Foo.swift"
    assert adopted.provenance["model_id"] == "test-model"


def test_second_classify_is_a_plain_hit(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "A/Foo.swift")
    _seed_old(cache, src, "old/A/Foo.swift", "A/Foo.swift")
    classify_files_via_cache(_config(src), "security", ["A/Foo.swift"], cache)
    again = classify_files_via_cache(_config(src), "security", ["A/Foo.swift"], cache)
    assert again.adopted == 0 and again.misses == []


def test_different_basename_is_not_adopted(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "A/Bar.swift")
    _seed_old(cache, src, "A/Foo.swift", "A/Bar.swift")
    result = classify_files_via_cache(_config(src), "security", ["A/Bar.swift"], cache)
    assert result.misses == ["A/Bar.swift"] and result.adopted == 0


def test_role_change_is_not_adopted(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "src/Foo.swift")
    _seed_old(cache, src, "tests/Foo.swift", "src/Foo.swift")
    result = classify_files_via_cache(_config(src), "security", ["src/Foo.swift"], cache)
    assert result.misses == ["src/Foo.swift"] and result.adopted == 0


def test_other_dimension_is_not_adopted(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "A/Foo.swift")
    _seed_old(cache, src, "old/Foo.swift", "A/Foo.swift", dim="reliability")
    result = classify_files_via_cache(_config(src), "security", ["A/Foo.swift"], cache)
    assert result.misses == ["A/Foo.swift"] and result.adopted == 0


def test_bypass_reads_never_adopts(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "A/Foo.swift")
    _seed_old(cache, src, "old/Foo.swift", "A/Foo.swift")
    result = classify_files_via_cache(
        _config(src), "security", ["A/Foo.swift"], cache, bypass_reads=True,
    )
    assert result.misses == ["A/Foo.swift"] and result.adopted == 0


def test_unconsolidated_source_adopts_as_unconsolidated(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "A/Foo.swift")
    _seed_old(cache, src, "old/Foo.swift", "A/Foo.swift", consolidated=False)
    result = classify_files_via_cache(_config(src), "security", ["A/Foo.swift"], cache)
    new_key = build_cache_key_for_file(_config(src), "A/Foo.swift", "security")
    assert result.cached_findings == []
    assert [f["file"] for f in result.unconsolidated_findings] == ["A/Foo.swift"]
    assert result.unconsolidated_hit_keys == {"A/Foo.swift": new_key}
    assert cache.get(new_key).consolidated is False


def test_backend_without_find_by_content_is_a_plain_miss(tmp_path: Path):
    class Plain:
        def __init__(self) -> None:
            self.store: dict[str, CacheEntry] = {}

        def get(self, key):
            return self.store.get(key)

        def put(self, key, entry):
            self.store[key] = entry

        def has(self, key):
            return key in self.store

        def delete(self, key):
            self.store.pop(key, None)

        def stats(self):
            return None

    src = tmp_path / "repo"
    _write(src, "A/Foo.swift")
    result = classify_files_via_cache(_config(src), "security", ["A/Foo.swift"], Plain())
    assert result.misses == ["A/Foo.swift"] and result.adopted == 0


def test_stale_index_row_is_verified_and_skipped(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    _write(src, "A/Foo.swift")
    old_key = _seed_old(cache, src, "old/Foo.swift", "A/Foo.swift")
    # Corrupt the pointed-at entry's hash without touching the index row.
    entry = cache.get(old_key)
    cache.put(old_key, replace(entry, file_content_hash="ff" * 32), index=False)
    result = classify_files_via_cache(_config(src), "security", ["A/Foo.swift"], cache)
    assert result.misses == ["A/Foo.swift"] and result.adopted == 0


def test_empty_content_hash_never_adopts(tmp_path: Path, cache: LocalFileBackend):
    src = tmp_path / "repo"
    src.mkdir()
    # File missing on disk: content hash is "", must be a plain miss.
    result = classify_files_via_cache(_config(src), "security", ["A/Missing.swift"], cache)
    assert result.misses == ["A/Missing.swift"] and result.adopted == 0


def test_adoption_picks_a_surviving_identical_sibling(tmp_path: Path, cache: LocalFileBackend):
    # Identical files at several paths (empty __init__.py, repeated
    # Package.swift) are a normal case: a still-present sibling with the same
    # bytes, basename and role is an equivalent source.
    src = tmp_path / "repo"
    _write(src, "Modules/A/Package.swift", "// swift-tools-version:5.9")
    _write(src, "Modules/B/Package.swift", "// swift-tools-version:5.9")
    _seed_old(cache, src, "Modules/A/Package.swift", "Modules/B/Package.swift")
    result = classify_files_via_cache(
        _config(src), "security", ["Modules/B/Package.swift"], cache,
    )
    assert result.misses == [] and result.adopted == 1
