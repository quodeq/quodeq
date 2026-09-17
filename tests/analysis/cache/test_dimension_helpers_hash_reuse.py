"""Regression tests for finding 5398: classify_files_via_cache exposes the
content hash it already computed for each miss (via build_cache_key_struct),
so the caller can hand it to the cache writer instead of re-hashing the file.

Sibling of test_dimension_helpers.py, which is already over the file-length
threshold -- kept separate rather than grown.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import CacheEntry, LocalFileBackend
from quodeq.analysis.cache.dimension_helpers import (
    build_cache_key_for_file,
    classify_files_via_cache,
)
from quodeq.analysis.fingerprint import _hash_file


def _make_config(src: Path) -> RunConfig:
    opts = AnalysisOptions(subagent_model="test-model")
    return RunConfig(src=src, language="python", work_dir=src, options=opts)


def _write_files(root: Path, contents: dict[str, str]) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        (root / name).write_text(text)
    return sorted(contents.keys())


def test_classify_returns_miss_hashes_for_every_miss(tmp_path: Path):
    cache = LocalFileBackend(root=tmp_path / "cache")
    files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
    config = _make_config(tmp_path / "src")

    result = classify_files_via_cache(config, "security", files, cache)

    assert result.misses == files
    assert set(result.miss_hashes.keys()) == set(files)
    for f in files:
        assert result.miss_hashes[f] == (_hash_file(config.src / f) or "")


def test_classify_omits_hits_from_miss_hashes(tmp_path: Path):
    cache = LocalFileBackend(root=tmp_path / "cache")
    files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
    config = _make_config(tmp_path / "src")
    key_a = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key_a, CacheEntry(
        key=key_a, schema_version=1, findings=[],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model",
    ))

    result = classify_files_via_cache(config, "security", files, cache)

    assert result.misses == ["b.py"]
    assert set(result.miss_hashes.keys()) == {"b.py"}
    assert result.miss_hashes["b.py"] == (_hash_file(config.src / "b.py") or "")
