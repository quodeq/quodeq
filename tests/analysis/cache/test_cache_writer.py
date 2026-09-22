"""Unit tests for the build_cache_writer factory: entries written, keys, traversal, consolidation.

The factory produces a closure that writes per-file cache entries when
invoked. The closure is intended to be passed as FindingsRouter's on_file_done
callback, fired synchronously on each mark_file_done(status="ok").
"""
from __future__ import annotations

import json

from quodeq.config.paths import default_paths

from ._cache_writer_helpers import _make_config


def test_cache_writer_writes_entry_via_local_backend(tmp_path):
    """build_cache_writer returns a closure that writes a per-file cache entry."""
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))

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
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Empty.kt").write_text("// empty")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))

    write("Empty.kt", [])

    entries = list(cache_root.rglob("entry.json"))
    assert len(entries) == 1


def test_cache_writer_key_matches_classify_files_via_cache(tmp_path):
    """LOAD-BEARING TEST: the key the closure computes MUST equal
    build_cache_key_for_file(config, file, dim). Otherwise the parent's
    classify_files_via_cache will MISS what the closure WRITES, and we'd be
    back to the same divergence Phase 1 was meant to fix.

    Verifies the fingerprint contract: same inputs -> same key -> same finding.
    """
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"

    config = _make_config(src_root, work_dir=tmp_path, model="sonnet", language="kotlin")

    expected_key = build_cache_key_for_file(config, "Foo.kt", "flexibility")

    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))
    write("Foo.kt", [{"file": "Foo.kt", "line": 1, "p": "X", "t": "violation", "req": "R-1"}])

    cache = LocalFileBackend(root=cache_root)
    entry = cache.get(expected_key)
    assert entry is not None, (
        f"Cache writer must produce the same key as build_cache_key_for_file. "
        f"Expected key {expected_key!r} not found in cache_root={cache_root}."
    )
    assert entry.file_path == "Foo.kt"
    assert len(entry.findings) == 1


def test_cache_writer_path_traversal_yields_empty_hash(tmp_path):
    """A traversal file_path (e.g. '../outside/secret.txt') must NOT hash a
    file outside src_root. The resulting cache entry's file_content_hash must
    be empty, not a real hash of the escaped file."""

    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer

    # Create a sentinel file OUTSIDE src_root with known content.
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    sentinel = outside_dir / "secret.txt"
    sentinel.write_text("TOP SECRET")

    src_root = tmp_path / "src"
    src_root.mkdir()

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="flexibility",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))

    # Craft a traversal path that resolves to the sentinel outside src_root.
    traversal_path = "../outside/secret.txt"
    write(traversal_path, [])

    entries = list(cache_root.rglob("entry.json"))
    assert len(entries) == 1, f"Expected 1 cache entry, found {len(entries)}"
    # Read the entry JSON directly -- the key computed with an empty hash
    # differs from build_cache_key_for_file (which still reads the outside file),
    # so we inspect the stored JSON rather than doing a cache.get() lookup.
    entry_data = json.loads(entries[0].read_text())
    # The hash must be empty -- the outside file must NOT have been read.
    assert entry_data.get("file_content_hash") == "", (
        f"Expected empty content hash for traversal path, "
        f"got {entry_data.get('file_content_hash')!r}"
    )


def test_cache_writer_marks_the_entry_unconsolidated(tmp_path):
    """A freshly produced finding has not reached any completed run's report
    yet. The entry is born unconsolidated and stays that way until the run
    that produced it reaches done."""
    from quodeq.analysis.cache.cache_writer import CacheWriterSpec, build_cache_writer
    from quodeq.analysis.cache.local import LocalFileBackend

    src_root = tmp_path / "src"
    src_root.mkdir()
    (src_root / "Foo.kt").write_text("class Foo")

    cache_root = tmp_path / "cache"
    write = build_cache_writer(CacheWriterSpec(
        cache_root=cache_root,
        src_root=src_root,
        standards_dir=None,
        dimension="security",
        model_id="sonnet",
        language="kotlin",
        prompts_dir=default_paths().prompts_dir,
    ))
    write("Foo.kt", [{"file": "Foo.kt", "line": 1, "t": "violation"}])

    backend = LocalFileBackend(root=cache_root)
    entries = [
        # LocalFileBackend shards keys as <root>/key[:2]/key[2:]/entry.json,
        # so the full key is the two parent directory names concatenated.
        backend.get(p.parent.parent.name + p.parent.name)
        for p in cache_root.rglob("entry.json")
    ]
    written = [e for e in entries if e is not None]
    assert written, "expected the writer to persist one entry"
    assert all(e.consolidated is False for e in written)
