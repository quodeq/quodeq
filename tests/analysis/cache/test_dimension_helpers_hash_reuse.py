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
from quodeq.analysis.cache._persist_watcher import CachePersistProvenance
from quodeq.analysis.cache.dimension_helpers import (
    CacheEntryTarget,
    _build_cache_entry_for_file,
    build_cache_key_for_file,
    classify_files_via_cache,
)
from quodeq.analysis.fingerprint import hash_file, stat_key


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
        assert result.miss_hashes[f] == (hash_file(config.src / f) or "")


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
    assert result.miss_hashes["b.py"] == (hash_file(config.src / "b.py") or "")


def test_classify_records_a_stat_stamp_beside_every_miss_hash(tmp_path: Path):
    """Finding 3: the hash is only reusable while the file is provably the one
    classify hashed, so classify records the stamp it read it under."""
    cache = LocalFileBackend(root=tmp_path / "cache")
    files = _write_files(tmp_path / "src", {"a.py": "x"})
    config = _make_config(tmp_path / "src")

    result = classify_files_via_cache(config, "security", files, cache)

    assert result.miss_stamps == {"a.py": stat_key(config.src / "a.py")}


def _entry_for(config: RunConfig, content_hash: str, content_stamp) -> CacheEntry:
    target = CacheEntryTarget(
        file_path="a.py", key="k", model_id="m", version="v",
        content_hash=content_hash, content_stamp=content_stamp,
    )
    return _build_cache_entry_for_file(
        config, "security", target, {},
        CachePersistProvenance(
            standards_hash="", params_hash="", effective_params={}, prompts_hash="",
        ),
    )


def test_persist_rehashes_when_the_file_changed_after_classify(tmp_path: Path):
    """The dispatch-persist path shares the writer's guard: a file edited
    between classify and the write is keyed on the content analysed."""
    src = tmp_path / "src"
    _write_files(src, {"a.py": "x"})
    config = _make_config(src)
    stamp = stat_key(src / "a.py")

    (src / "a.py").write_text("x = edited between classify and persist")
    entry = _entry_for(config, "classify-time-hash", stamp)

    assert entry.file_content_hash == hash_file(src / "a.py")


def test_persist_reuses_the_hash_while_the_stamp_still_matches(tmp_path: Path):
    src = tmp_path / "src"
    _write_files(src, {"a.py": "x"})
    config = _make_config(src)

    entry = _entry_for(config, "classify-time-hash", stat_key(src / "a.py"))

    assert entry.file_content_hash == "classify-time-hash"


def test_persist_rehashes_an_unstamped_hash(tmp_path: Path):
    src = tmp_path / "src"
    _write_files(src, {"a.py": "x"})
    config = _make_config(src)

    entry = _entry_for(config, "classify-time-hash", None)

    assert entry.file_content_hash == hash_file(src / "a.py")
