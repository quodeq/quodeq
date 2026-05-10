"""Dimension-level cache helpers — pure functions that bridge between
RunConfig + filesystem and the cache layer.

This is the building block for Phase B5's wiring. Three helpers:

  - build_cache_key_for_file: derive the cache key from RunConfig + file
  - classify_files_via_cache: split files into hits and misses
  - persist_dispatch_results: after dispatch, write per-file entries

Tests use the real cache backend with synthetic RunConfigs. No live
dispatch needed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.analysis.cache import LocalFileBackend, CacheEntry
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    build_cache_key_for_file,
    classify_files_via_cache,
    persist_dispatch_results,
)


def _write_files(root: Path, contents: dict[str, str]) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return sorted(contents.keys())


def _make_config(
    src: Path, *, work_dir: Path | None = None,
    standards_dir: Path | None = None, model: str = "test-model",
    language: str = "python",
) -> RunConfig:
    opts = AnalysisOptions(subagent_model=model)
    return RunConfig(
        src=src, language=language, standards_dir=standards_dir,
        work_dir=work_dir or src, options=opts,
    )


def _write_compiled_standards(standards_dir: Path, dim: str, payload: str) -> None:
    compiled = standards_dir / "compiled"
    compiled.mkdir(parents=True, exist_ok=True)
    (compiled / f"{dim}.json").write_text(payload)


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


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

    def test_model_change_invalidates(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        c1 = _make_config(tmp_path / "src", model="claude-opus-4-7")
        c2 = _make_config(tmp_path / "src", model="claude-sonnet-4-6")
        assert (
            build_cache_key_for_file(c1, "a.py", "security")
            != build_cache_key_for_file(c2, "a.py", "security")
        )

    def test_language_change_invalidates(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        c1 = _make_config(tmp_path / "src", language="python")
        c2 = _make_config(tmp_path / "src", language="typescript")
        assert (
            build_cache_key_for_file(c1, "a.py", "security")
            != build_cache_key_for_file(c2, "a.py", "security")
        )

    def test_standards_change_invalidates(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        std_dir = tmp_path / "standards"
        _write_compiled_standards(std_dir, "security", '{"v": 1}')
        c1 = _make_config(tmp_path / "src", standards_dir=std_dir)
        k1 = build_cache_key_for_file(c1, "a.py", "security")

        _write_compiled_standards(std_dir, "security", '{"v": 2}')
        k2 = build_cache_key_for_file(c1, "a.py", "security")
        assert k1 != k2

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


# ============================================================
# persist_dispatch_results
# ============================================================

class TestPersist:
    def test_writes_per_file_entry_from_jsonl(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work")
        miss_keys = {f: build_cache_key_for_file(config, f, "security") for f in files}

        # Simulate a dispatch run: JSONL has findings for both files.
        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            json.dumps({"file": "a.py", "line": 1, "t": "violation", "w": "a-issue"}) + "\n"
            + json.dumps({"file": "b.py", "line": 2, "t": "compliance", "w": "b-ok"}) + "\n"
            + json.dumps({"file": "a.py", "line": 5, "t": "violation", "w": "a-issue-2"}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n"
        )

        persist_dispatch_results(
            config, "security", miss_files=files,
            jsonl_path=jsonl, miss_keys=miss_keys, cache=cache,
        )

        a_entry = cache.get(miss_keys["a.py"])
        b_entry = cache.get(miss_keys["b.py"])
        assert a_entry is not None
        assert b_entry is not None
        assert len(a_entry.findings) == 2
        assert len(b_entry.findings) == 1
        assert a_entry.findings[0]["w"] == "a-issue"

    def test_empty_findings_still_written(self, tmp_path: Path, cache: LocalFileBackend):
        # A successful analysis that found nothing must cache an empty
        # entry so the next run hits instead of re-dispatching.
        files = _write_files(tmp_path / "src", {"clean.py": "x"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work")
        miss_keys = {f: build_cache_key_for_file(config, f, "security") for f in files}

        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        # No findings for clean.py — just the ok marker to confirm it completed.
        jsonl.write_text(
            json.dumps({"_marker": "file_done", "file": "clean.py", "status": "ok"}) + "\n"
        )

        persist_dispatch_results(
            config, "security", miss_files=files,
            jsonl_path=jsonl, miss_keys=miss_keys, cache=cache,
        )

        entry = cache.get(miss_keys["clean.py"])
        assert entry is not None
        assert entry.findings == []

    def test_only_writes_for_miss_files(self, tmp_path: Path, cache: LocalFileBackend):
        # JSONL might contain findings for files that weren't in misses
        # (e.g. carry-forward findings). We only cache entries for the
        # missed files we actually dispatched.
        files = _write_files(tmp_path / "src", {"a.py": "x", "carried.py": "y"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work")
        miss_keys = {"a.py": build_cache_key_for_file(config, "a.py", "security")}

        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            json.dumps({"file": "a.py", "line": 1}) + "\n"
            + json.dumps({"file": "carried.py", "line": 2}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
        )

        persist_dispatch_results(
            config, "security", miss_files=["a.py"],
            jsonl_path=jsonl, miss_keys=miss_keys, cache=cache,
        )

        # Only a.py's key is in the cache; carried.py was never dispatched here.
        assert cache.get(miss_keys["a.py"]) is not None
        # No entry for carried.py — its key isn't even in miss_keys.

    def test_handles_missing_jsonl(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work")
        miss_keys = {"a.py": build_cache_key_for_file(config, "a.py", "security")}

        # JSONL doesn't exist (e.g. dispatch failed before writing).
        persist_dispatch_results(
            config, "security", miss_files=["a.py"],
            jsonl_path=tmp_path / "work" / "missing.jsonl",
            miss_keys=miss_keys, cache=cache,
        )

        # No entry written — we don't fabricate "no findings" when we
        # have no evidence the analysis actually ran.
        assert cache.get(miss_keys["a.py"]) is None


# ============================================================
# end-to-end roundtrip
# ============================================================

class TestRoundTrip:
    def test_classify_dispatch_persist_then_classify_all_hits(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work")

        # First call: empty cache → all misses.
        first = classify_files_via_cache(config, "security", files, cache)
        assert sorted(first.misses) == files

        # Simulate dispatch: write JSONL with findings for the misses.
        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            json.dumps({"file": "a.py", "line": 1, "t": "violation"}) + "\n"
            + json.dumps({"file": "b.py", "line": 2, "t": "compliance"}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
            + json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n"
        )

        # Persist results.
        persist_dispatch_results(
            config, "security", miss_files=first.misses,
            jsonl_path=jsonl, miss_keys=first.miss_keys, cache=cache,
        )

        # Second call: cache should be fully populated → all hits.
        second = classify_files_via_cache(config, "security", files, cache)
        assert second.misses == []
        assert {f["file"] for f in second.cached_findings} == set(files)
