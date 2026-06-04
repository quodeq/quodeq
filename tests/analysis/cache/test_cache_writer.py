"""Unit tests for the build_cache_writer factory.

The factory produces a closure that writes per-file cache entries when
invoked. The closure is intended to be passed as FindingsRouter's on_file_done
callback, fired synchronously on each mark_file_done(status="ok").
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig


def _make_config(
    src: Path,
    *,
    work_dir: Path | None = None,
    standards_dir: Path | None = None,
    model: str = "sonnet",
    language: str = "kotlin",
) -> RunConfig:
    opts = AnalysisOptions(subagent_model=model)
    return RunConfig(
        src=src,
        language=language,
        standards_dir=standards_dir,
        work_dir=work_dir or src,
        options=opts,
    )


def test_cache_writer_writes_entry_via_local_backend(tmp_path):
    """build_cache_writer returns a closure that writes a per-file cache entry."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
    )

    findings = [{"file": "Foo.kt", "line": 10, "p": "Adaptability", "t": "violation", "req": "F-ADP-1"}]
    write("Foo.kt", findings)

    entries = list(cache_root.rglob("entry.json"))
    assert len(entries) == 1, f"Expected 1 cache entry under {cache_root}, found {len(entries)}"
    entry_json = entries[0].read_text()
    assert "Foo.kt" in entry_json
    assert "Adaptability" in entry_json


def test_cache_writer_writes_empty_findings_entry(tmp_path):
    """A file with no findings is still cached -- empty list is a valid result.
    This is what makes cache hits work on 'nothing-to-find' files."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Empty.kt").write_text("// empty")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
    )

    write("Empty.kt", [])

    entries = list(cache_root.rglob("entry.json"))
    assert len(entries) == 1


def test_cache_writer_records_provenance_and_content_hash(tmp_path):
    """The written entry is self-describing: it stores the file_content_hash
    it was keyed under and a provenance block (model / prompts / standards /
    quodeq version) recording the volatile context it was produced under."""
    import quodeq
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import (
        _hash_prompts_combined,
        build_cache_key_for_file,
    )
    from quodeq.analysis.cache.local import LocalFileBackend
    from quodeq.analysis.fingerprint import _hash_file

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
    )
    write("Foo.kt", [])

    config = _make_config(src_root, model="sonnet", language="kotlin")
    key = build_cache_key_for_file(config, "Foo.kt", "flexibility")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None
    assert entry.file_content_hash == _hash_file(src_root / "Foo.kt")
    prov = entry.provenance
    assert prov["model_id"] == "sonnet"
    assert prov["standards_hash"] == ""  # standards_dir=None
    assert prov["prompts_hash"] == _hash_prompts_combined()
    assert prov["quodeq_version"] == (quodeq.__version__ or "")


def test_entry_is_self_describing_for_future_key_migration(tmp_path):
    """The schema-3 self-describing guarantee: an entry stores EVERY field its
    key was computed from (content hash, path, dimension, language), so a
    future key change can be recomputed losslessly from the entry alone — no
    re-evaluation. This is what makes the 2->3 change the last one that costs
    a re-eval. Regressing it (e.g. dropping language from the entry) silently
    breaks future migratability, so pin it."""
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.key import CacheKey, compute_key
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(
        cache_root=cache_root, src_root=src_root, standards_dir=None,
        dimension="flexibility", model_id="sonnet", language="kotlin",
    )
    write("Foo.kt", [])

    config = _make_config(src_root, model="sonnet", language="kotlin")
    key = build_cache_key_for_file(config, "Foo.kt", "flexibility")
    entry = LocalFileBackend(root=cache_root).get(key)
    assert entry is not None

    # Recompute the key PURELY from stored entry fields (the migration
    # primitive — a real migration does this with schema_version + 1).
    recomputed = compute_key(CacheKey(
        schema_version=entry.schema_version,
        file_content_hash=entry.file_content_hash,
        file_path=entry.file_path,
        dimension=entry.dimension,
        language=entry.language,
    ))
    assert recomputed == key


def test_cache_writer_key_matches_classify_files_via_cache(tmp_path):
    """LOAD-BEARING TEST: the key the closure computes MUST equal
    build_cache_key_for_file(config, file, dim). Otherwise the parent's
    classify_files_via_cache will MISS what the closure WRITES, and we'd be
    back to the same divergence Phase 1 was meant to fix.

    Verifies the fingerprint contract: same inputs -> same key -> same finding.
    """
    from quodeq.analysis.cache.cache_writer import build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"

    config = _make_config(src_root, work_dir=tmp_path, model="sonnet", language="kotlin")

    expected_key = build_cache_key_for_file(config, "Foo.kt", "flexibility")

    write = build_cache_writer(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
    )
    write("Foo.kt", [{"file": "Foo.kt", "line": 1, "p": "X", "t": "violation", "req": "R-1"}])

    cache = LocalFileBackend(root=cache_root)
    entry = cache.get(expected_key)
    assert entry is not None, (
        f"Cache writer must produce the same key as build_cache_key_for_file. "
        f"Expected key {expected_key!r} not found in cache_root={cache_root}."
    )
    assert entry.file_path == "Foo.kt"
    assert len(entry.findings) == 1
