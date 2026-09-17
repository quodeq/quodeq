"""Regression tests for finding 5398: the cache-write closure reuses the
content hash the classify step already computed for a miss, instead of
re-hashing the file's full content a second time.

Sibling of test_cache_writer.py, which is already over the file-length
threshold -- kept separate rather than grown.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.config.paths import default_paths


def _build_spec(cache_root: Path, src_root: Path, *, content_hashes=None):
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec

    kwargs = dict(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    )
    if content_hashes is not None:
        kwargs["content_hashes"] = content_hashes
    return CacheWriterSpec(**kwargs)


def test_writer_uses_the_classify_time_hash_instead_of_rehashing(tmp_path, monkeypatch):
    """The closure must use the hash classify already computed for a miss
    rather than reading and re-hashing the file a second time."""
    from quodeq.analysis.cache import cache_writer
    from quodeq.analysis.cache.key import CacheKey, compute_key
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "a.py").write_text("class Foo")

    def _boom(*_args, **_kwargs):
        raise AssertionError("re-hashed")

    monkeypatch.setattr(cache_writer, "_hash_file", _boom)

    cache_root = tmp_path / "cache"
    write = cache_writer.build_cache_writer(_build_spec(
        cache_root, src_root, content_hashes={"a.py": "abc123"},
    ))
    write("a.py", [])

    expected_key = compute_key(CacheKey(
        schema_version=cache_writer._SCHEMA_VERSION,
        file_content_hash="abc123",
        file_path="a.py",
        dimension="flexibility",
        params_hash="",
    ))
    entry = LocalFileBackend(root=cache_root).get(expected_key)
    assert entry is not None, "entry not found under the classify-time-hash key"
    assert entry.file_content_hash == "abc123"


def test_writer_hashes_when_no_classify_time_hash_is_known(tmp_path):
    """A file absent from content_hashes (e.g. no ClassifyResult in scope)
    falls back to hashing it directly, matching the pre-existing behaviour."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis._types import AnalysisOptions, RunConfig
    from quodeq.analysis.fingerprint import _hash_file

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "a.py").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(_build_spec(cache_root, src_root))
    write("a.py", [])

    config = RunConfig(
        src=src_root, language="kotlin", work_dir=src_root,
        options=AnalysisOptions(subagent_model="sonnet"),
    )
    key = build_cache_key_for_file(config, "a.py", "flexibility")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None
    assert entry.file_content_hash == _hash_file(src_root / "a.py")
