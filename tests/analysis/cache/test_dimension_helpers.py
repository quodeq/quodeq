"""Dimension-level cache helpers: build_cache_key_for_file and classify_files_via_cache.

Tests use the real cache backend with synthetic RunConfigs. No live
dispatch needed. Provenance and persist behaviour live in the
test_dimension_helpers_* siblings.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.cache import CacheEntry, LocalFileBackend
from quodeq.analysis.cache.dimension_helpers import (
    build_cache_key_for_file,
    classify_files_via_cache,
)

from ._dimension_helpers_helpers import (
    _make_config,
    _write_compiled_standards,
    _write_files,
)


# ============================================================
# build_cache_key_for_file
# ============================================================

class TestKeyComposition:
    def test_returns_64_hex_string(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src")
        key = build_cache_key_for_file(config, "a.py", "security")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_file_content_change_invalidates(self, tmp_path: Path):
        src = tmp_path / "src"
        _write_files(src, {"a.py": "version1"})
        config = _make_config(src)
        k1 = build_cache_key_for_file(config, "a.py", "security")

        (src / "a.py").write_text("version2")
        k2 = build_cache_key_for_file(config, "a.py", "security")
        assert k1 != k2

    def test_dimension_change_invalidates(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src")
        assert (
            build_cache_key_for_file(config, "a.py", "security")
            != build_cache_key_for_file(config, "a.py", "documentation")
        )

    def test_model_change_does_not_invalidate(self, tmp_path: Path):
        # Permissive key: switching model reuses the cache (model lives in
        # provenance, not the key). This is the cost-first behavior.
        _write_files(tmp_path / "src", {"a.py": "x"})
        c1 = _make_config(tmp_path / "src", model="claude-opus-4-7")
        c2 = _make_config(tmp_path / "src", model="claude-sonnet-4-6")
        assert (
            build_cache_key_for_file(c1, "a.py", "security")
            == build_cache_key_for_file(c2, "a.py", "security")
        )

    def test_language_change_does_not_invalidate(self, tmp_path: Path):
        # Schema 4: language left the key. It only ever reached the prompt
        # as a heading word, so a detect_language() flip must not re-key
        # the whole repo (freemium-app-android, java -> kotlin, Sep 2026).
        _write_files(tmp_path / "src", {"a.py": "x"})
        c1 = _make_config(tmp_path / "src", language="python")
        c2 = _make_config(tmp_path / "src", language="typescript")
        assert (
            build_cache_key_for_file(c1, "a.py", "security")
            == build_cache_key_for_file(c2, "a.py", "security")
        )

    def test_standards_change_does_not_invalidate(self, tmp_path: Path):
        # Permissive key: editing a standard reuses the cache. Standards drift
        # is surfaced via provenance, and the user refreshes with --clean-scan
        # when they want to re-evaluate against new standards.
        _write_files(tmp_path / "src", {"a.py": "x"})
        std_dir = tmp_path / "standards"
        _write_compiled_standards(std_dir, "security", '{"v": 1}')
        c1 = _make_config(tmp_path / "src", standards_dir=std_dir)
        k1 = build_cache_key_for_file(c1, "a.py", "security")

        _write_compiled_standards(std_dir, "security", '{"v": 2}')
        import os
        compiled = std_dir / "compiled" / "security.json"
        st = compiled.stat()
        os.utime(compiled, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        k2 = build_cache_key_for_file(c1, "a.py", "security")
        assert k1 == k2

    def test_path_change_invalidates(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x", "sub/a.py": "x"})
        config = _make_config(tmp_path / "src")
        # Same content, different paths → distinct keys.
        assert (
            build_cache_key_for_file(config, "a.py", "security")
            != build_cache_key_for_file(config, "sub/a.py", "security")
        )

    def test_stable_across_calls(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src")
        assert (
            build_cache_key_for_file(config, "a.py", "security")
            == build_cache_key_for_file(config, "a.py", "security")
        )


# ============================================================
# classify_files_via_cache
# ============================================================

class TestClassify:
    def test_empty_cache_all_misses(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
        config = _make_config(tmp_path / "src")
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.cached_findings == []
        assert sorted(result.misses) == files
        assert set(result.miss_keys.keys()) == set(files)

    def test_full_cache_all_hits(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
        config = _make_config(tmp_path / "src")
        # Pre-populate cache for both files.
        canned: dict[str, list[dict]] = {
            "a.py": [{"file": "a.py", "line": 1, "t": "violation"}],
            "b.py": [{"file": "b.py", "line": 2, "t": "compliance"}],
        }
        for f in files:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1, findings=canned[f],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        result = classify_files_via_cache(config, "security", files, cache)
        assert result.misses == []
        assert {f["file"] for f in result.cached_findings} == set(files)

    def test_partial_cache_split(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y", "c.py": "z"})
        config = _make_config(tmp_path / "src")
        # Only b.py is cached.
        key_b = build_cache_key_for_file(config, "b.py", "security")
        cache.put(key_b, CacheEntry(
            key=key_b, schema_version=1,
            findings=[{"file": "b.py", "line": 1, "t": "violation"}],
            files_read=1, file_path="b.py", dimension="security",
            model_id="test-model",
        ))

        result = classify_files_via_cache(config, "security", files, cache)
        assert sorted(result.misses) == ["a.py", "c.py"]
        assert [f["file"] for f in result.cached_findings] == ["b.py"]

    def test_modified_file_invalidates_hit(self, tmp_path: Path, cache: LocalFileBackend):
        src = tmp_path / "src"
        files = _write_files(src, {"a.py": "v1"})
        config = _make_config(src)
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1, findings=[{"file": "a.py"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        # Modify file → key changes → miss.
        (src / "a.py").write_text("v2")
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.misses == ["a.py"]
        assert result.cached_findings == []


def test_classify_splits_hits_by_consolidation_state(tmp_path):
    """A hit from a run that never completed must stay out of cached_findings,
    so the replay path does not stamp it carried_forward."""
    from quodeq.analysis.cache.dimension_helpers import (
        build_cache_key_for_file,
        classify_files_via_cache,
    )
    from quodeq.analysis.cache.entry import CacheEntry
    from quodeq.analysis.cache.local import LocalFileBackend

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x")
    (src / "b.py").write_text("y")
    config = _make_config(src)

    cache = LocalFileBackend(root=tmp_path / "cache")
    for name, consolidated in (("a.py", True), ("b.py", False)):
        key = build_cache_key_for_file(config, name, "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": name, "line": 1, "t": "violation", "p": "P1"}],
            files_read=1, file_path=name, dimension="security",
            model_id="test-model", consolidated=consolidated,
        ))

    result = classify_files_via_cache(
        config, "security", ["a.py", "b.py"], cache,
    )

    assert result.misses == []
    assert [f["file"] for f in result.cached_findings] == ["a.py"]
    assert [f["file"] for f in result.unconsolidated_findings] == ["b.py"]
    assert set(result.unconsolidated_hit_keys) == {"b.py"}
    assert result.unconsolidated_hit_keys["b.py"] == build_cache_key_for_file(
        config, "b.py", "security",
    )


def test_classify_leaves_unconsolidated_fields_empty_when_all_hits_consolidated(tmp_path):
    from quodeq.analysis.cache.dimension_helpers import (
        build_cache_key_for_file,
        classify_files_via_cache,
    )
    from quodeq.analysis.cache.entry import CacheEntry
    from quodeq.analysis.cache.local import LocalFileBackend

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x")
    config = _make_config(src)

    cache = LocalFileBackend(root=tmp_path / "cache")
    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[{"file": "a.py", "line": 1, "t": "violation", "p": "P1"}],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model", consolidated=True,
    ))

    result = classify_files_via_cache(config, "security", ["a.py"], cache)

    assert result.unconsolidated_findings == []
    assert result.unconsolidated_hit_keys == {}


def test_classify_treats_a_legacy_entry_as_consolidated(tmp_path):
    """An entry stored before the field existed has no consolidated key.
    from_json defaults it True, so it must land in cached_findings."""
    from quodeq.analysis.cache.dimension_helpers import (
        build_cache_key_for_file,
        classify_files_via_cache,
    )
    from quodeq.analysis.cache.entry import CacheEntry
    from quodeq.analysis.cache.local import LocalFileBackend

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x")
    config = _make_config(src)

    cache = LocalFileBackend(root=tmp_path / "cache")
    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[{"file": "a.py", "line": 1, "t": "violation", "p": "P1"}],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model",
    ))

    result = classify_files_via_cache(config, "security", ["a.py"], cache)

    assert [f["file"] for f in result.cached_findings] == ["a.py"]
    assert result.unconsolidated_findings == []
