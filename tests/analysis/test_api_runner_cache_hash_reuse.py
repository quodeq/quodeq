"""Regression tests: _build_cache_writer threads the
dimension's classify-time content hashes (stashed on RunConfig by
classify_files_via_cache) through to the cache-write closure, so the write
path reuses the hash classify already computed instead of re-hashing.

Sibling of test_api_runner.py / test_api_runner_coverage.py, both already
over the file-length threshold -- kept separate rather than grown.
"""
from __future__ import annotations

from quodeq.analysis._api_runner import _build_cache_writer
from quodeq.analysis.run_types import AnalysisOptions, ClassifyStash, RunConfig
from quodeq.analysis.cache.dimension_helpers import ClassifyResult
from quodeq.analysis.cache.key import CacheKey, compute_key
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.fingerprint import hash_file, stat_key


def _run_config(src_root, *, classify_cache=None):
    return RunConfig(
        src=src_root, language="kotlin", work_dir=src_root,
        options=AnalysisOptions(subagent_model="sonnet"),
        classify_stash=classify_cache,
    )


def test_build_cache_writer_reuses_the_stashed_classify_time_hash(tmp_path, monkeypatch):
    """When classify_files_via_cache has already stashed a ClassifyResult for
    this dimension, the writer built for it must use miss_hashes rather than
    re-hashing the file -- as long as the stamp beside the hash still matches
    the file on disk (finding 3)."""
    from quodeq.analysis.cache import _key_provenance, cache_writer as cache_writer_module

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")
    cache_base = tmp_path / "cache"
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(cache_base))
    cache_root = cache_base / "results"

    def _boom(*_args, **_kwargs):
        raise AssertionError("re-hashed")

    monkeypatch.setattr(_key_provenance, "hash_file", _boom)

    classify = ClassifyResult(
        misses=["Foo.kt"], miss_hashes={"Foo.kt": "stashed-hash"},
        miss_stamps={"Foo.kt": stat_key(src_root / "Foo.kt")},
    )
    run_config = _run_config(src_root, classify_cache={
        "flexibility": ClassifyStash(("Foo.kt",), classify),
    })

    write = _build_cache_writer(run_config, "flexibility")
    assert write is not None
    write("Foo.kt", [])

    expected_key = compute_key(CacheKey(
        schema_version=cache_writer_module.SCHEMA_VERSION,
        file_content_hash="stashed-hash",
        file_path="Foo.kt",
        dimension="flexibility",
        params_hash="",
    ))
    entry = LocalFileBackend(root=cache_root).get(expected_key)
    assert entry is not None, "entry not found under the classify-time-hash key"
    assert entry.file_content_hash == "stashed-hash"


def test_build_cache_writer_hashes_when_the_stash_has_no_entry(tmp_path, monkeypatch):
    """Without a matching stash (e.g. classify_cache disabled, or a different
    dimension), the writer falls back to hashing the file directly -- the
    pre-existing behaviour."""
    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")
    cache_base = tmp_path / "cache"
    monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(cache_base))
    cache_root = cache_base / "results"

    from quodeq.analysis.cache import cache_writer as cache_writer_module

    run_config = _run_config(src_root, classify_cache=None)

    write = _build_cache_writer(run_config, "flexibility")
    assert write is not None
    write("Foo.kt", [])

    expected_key = compute_key(CacheKey(
        schema_version=cache_writer_module.SCHEMA_VERSION,
        file_content_hash=hash_file(src_root / "Foo.kt") or "",
        file_path="Foo.kt",
        dimension="flexibility",
        params_hash="",
    ))
    entry = LocalFileBackend(root=cache_root).get(expected_key)
    assert entry is not None
    assert entry.file_content_hash == hash_file(src_root / "Foo.kt")
