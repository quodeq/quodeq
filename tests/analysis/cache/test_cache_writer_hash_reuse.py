"""Regression tests for finding 5398: the cache-write closure reuses the
content hash the classify step already computed for a miss, instead of
re-hashing the file's full content a second time.

Sibling of test_cache_writer.py, which is already over the file-length
threshold -- kept separate rather than grown.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.config.paths import default_paths


def _build_spec(cache_root: Path, src_root: Path, *, content_hashes=None, content_stamps=None):
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
    if content_stamps is not None:
        kwargs["content_stamps"] = content_stamps
    return CacheWriterSpec(**kwargs)


def _key_for(hash_: str) -> str:
    from quodeq.analysis.cache.cache_writer import _SCHEMA_VERSION
    from quodeq.analysis.cache.key import CacheKey, compute_key

    return compute_key(CacheKey(
        schema_version=_SCHEMA_VERSION,
        file_content_hash=hash_,
        file_path="a.py",
        dimension="flexibility",
        params_hash="",
    ))


def test_writer_uses_the_classify_time_hash_instead_of_rehashing(tmp_path, monkeypatch):
    """The closure must use the hash classify already computed for a miss
    rather than reading and re-hashing the file a second time.

    Reuse is conditional on the recorded stat stamp still matching (finding
    3), so the spec carries the stamp classify took alongside the hash.
    """
    from quodeq.analysis.cache import _key_provenance, cache_writer
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import _stat_key

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "a.py").write_text("class Foo")

    def _boom(*_args, **_kwargs):
        raise AssertionError("re-hashed")

    monkeypatch.setattr(_key_provenance, "_hash_file", _boom)

    cache_root = tmp_path / "cache"
    write = cache_writer.build_cache_writer(_build_spec(
        cache_root, src_root, content_hashes={"a.py": "abc123"},
        content_stamps={"a.py": _stat_key(src_root / "a.py")},
    ))
    write("a.py", [])

    entry = LocalFileBackend(root=cache_root).get(_key_for("abc123"))
    assert entry is not None, "entry not found under the classify-time-hash key"
    assert entry.file_content_hash == "abc123"


def test_writer_hashes_when_no_classify_time_hash_is_known(tmp_path):
    """A file absent from content_hashes (e.g. no ClassifyResult in scope)
    falls back to hashing it directly, matching the pre-existing behaviour."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.run_types import AnalysisOptions, RunConfig
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


def test_writer_rehashes_when_the_file_changed_after_classify(tmp_path):
    """Finding 3: classify hashes at run start, so a file edited before this
    dimension was dispatched is analysed with the new content. The entry must
    then carry the fresh hash, not the one the stash holds."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import _hash_file, _stat_key

    src_root = tmp_path / "src"
    src_root.mkdir()
    target = src_root / "a.py"
    target.write_text("class Foo")
    stamp = _stat_key(target)

    cache_root = tmp_path / "cache"
    write = build_cache_writer(_build_spec(
        cache_root, src_root, content_hashes={"a.py": "classify-time-hash"},
        content_stamps={"a.py": stamp},
    ))
    target.write_text("class Foo:\n    pass  # edited between classify and dispatch")
    write("a.py", [])

    fresh = _hash_file(target)
    cache = LocalFileBackend(root=cache_root)
    assert cache.get(_key_for("classify-time-hash")) is None
    entry = cache.get(_key_for(fresh))
    assert entry is not None, "entry not keyed on the content that was analysed"
    assert entry.file_content_hash == fresh


def test_writer_rehashes_when_the_stash_has_no_stamp(tmp_path):
    """A stashed hash with no stamp beside it cannot be proven current, so it
    counts as unknown and the file is hashed at write time."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import _hash_file

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "a.py").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(_build_spec(
        cache_root, src_root, content_hashes={"a.py": "unstamped"},
    ))
    write("a.py", [])

    fresh = _hash_file(src_root / "a.py")
    cache = LocalFileBackend(root=cache_root)
    assert cache.get(_key_for("unstamped")) is None
    assert cache.get(_key_for(fresh)) is not None


def test_writer_rehashes_when_the_stashed_hash_is_empty(tmp_path):
    """Finding 7: an empty stashed hash is "unknown", not a usable key -- an
    entry keyed on "" is never adoptable and misses forever."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import _hash_file, _stat_key

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "a.py").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(_build_spec(
        cache_root, src_root, content_hashes={"a.py": ""},
        content_stamps={"a.py": _stat_key(src_root / "a.py")},
    ))
    write("a.py", [])

    fresh = _hash_file(src_root / "a.py")
    cache = LocalFileBackend(root=cache_root)
    assert cache.get(_key_for("")) is None
    entry = cache.get(_key_for(fresh))
    assert entry is not None
    assert entry.file_content_hash == fresh
