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
    format_provenance_drift,
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


def _write_project_overrides(src: Path, payload: str) -> None:
    path = src / ".quodeq" / "standards-overrides.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)


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

    def test_language_change_invalidates(self, tmp_path: Path):
        _write_files(tmp_path / "src", {"a.py": "x"})
        c1 = _make_config(tmp_path / "src", language="python")
        c2 = _make_config(tmp_path / "src", language="typescript")
        assert (
            build_cache_key_for_file(c1, "a.py", "security")
            != build_cache_key_for_file(c2, "a.py", "security")
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


# ============================================================
# provenance drift (reuse across model/standards/prompts boundary)
# ============================================================

class TestProvenanceDrift:
    def _seed(self, cache, config, files, *, provenance):
        for f in files:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=3, findings=[{"file": f}],
                files_read=1, file_path=f, dimension="security",
                model_id=provenance.get("model_id", ""), provenance=provenance,
            ))

    def test_reports_model_drift_across_hits(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x", "b.py": "y"})
        config = _make_config(tmp_path / "src", model="new-model")
        # Seed entries produced under a different model. Other provenance
        # fields are blank, so only the model field is a known difference.
        self._seed(cache, config, files, provenance={
            "model_id": "old-model", "standards_hash": "",
            "prompts_hash": "", "quodeq_version": "",
        })
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.misses == []
        drift = result.provenance_drift
        assert drift["model_id"]["count"] == 2
        assert drift["model_id"]["from"] == "old-model"
        assert drift["model_id"]["to"] == "new-model"
        # Blank (unknown) fields are never reported as drift.
        assert "standards_hash" not in drift
        assert "prompts_hash" not in drift

    def test_ignores_unknown_provenance(self, tmp_path: Path, cache: LocalFileBackend):
        # A legacy / empty-provenance entry must not be claimed as drift —
        # we can't know what it was produced under.
        files = _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src", model="new-model")
        self._seed(cache, config, files, provenance={})
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.misses == []
        assert result.provenance_drift == {}

    def test_reports_standards_drift_when_overrides_change(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # Threshold overrides fold into the standards hash: entries produced
        # before a project tuned .quodeq/standards-overrides.json must show
        # standards drift on reuse — the compiled JSON alone is unchanged.
        from quodeq.analysis.fingerprint import _hash_standards

        src = tmp_path / "src"
        files = _write_files(src, {"a.py": "x"})
        standards_dir = tmp_path / "standards"
        _write_compiled_standards(standards_dir, "security", '{"rule": "v1"}')
        config = _make_config(src, standards_dir=standards_dir)
        pre_override = _hash_standards(standards_dir, "security") or ""
        self._seed(cache, config, files, provenance={
            "model_id": "test-model", "standards_hash": pre_override,
            "prompts_hash": "", "quodeq_version": "",
        })

        _write_project_overrides(
            src, '{"version": 1, "overrides": {"S-INJ-1": {"max_lines": 60}}}',
        )
        result = classify_files_via_cache(config, "security", files, cache)

        # Reuse still happens (permissive key) but is flagged, not silent.
        assert result.misses == []
        assert result.provenance_drift["standards_hash"]["count"] == 1

    def test_no_drift_when_provenance_matches(self, tmp_path: Path, cache: LocalFileBackend):
        files = _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src", model="same-model")
        self._seed(cache, config, files, provenance={
            "model_id": "same-model", "standards_hash": "",
            "prompts_hash": "", "quodeq_version": "",
        })
        result = classify_files_via_cache(config, "security", files, cache)
        assert result.provenance_drift == {}


class TestFormatProvenanceDrift:
    def test_names_model_and_standards_with_counts(self):
        drift = {
            "model_id": {"count": 240, "from": "claude-sonnet-4", "to": "claude-opus-4"},
            "standards_hash": {"count": 240, "from": "s3", "to": "s4"},
        }
        msg = format_provenance_drift(drift, reused=240)
        assert "240" in msg
        assert "model" in msg
        assert "claude-sonnet-4" in msg and "claude-opus-4" in msg
        assert "standards" in msg
        # Opaque standards hashes are not dumped into user-facing text.
        assert "s3" not in msg
        # No em-dash in user-facing strings (repo convention).
        assert "—" not in msg

    def test_empty_when_no_drift(self):
        assert format_provenance_drift({}, reused=100) == ""

    def test_shows_version_transition_suppresses_all_hashes_in_order(self):
        # Covers the other two field branches: quodeq_version (human-value,
        # shows from->to) and prompts_hash (opaque, value suppressed). Pins
        # that NEITHER the 'from' nor 'to' of an opaque hash leaks, and that
        # fields render in _PROV_FIELDS order.
        drift = {
            "model_id": {"count": 3, "from": "sonnet", "to": "opus"},
            "standards_hash": {"count": 3, "from": "s3", "to": "s4"},
            "prompts_hash": {"count": 3, "from": "p3", "to": "p4"},
            "quodeq_version": {"count": 3, "from": "1.0.0", "to": "1.1.2"},
        }
        msg = format_provenance_drift(drift, reused=3)
        # Human-value fields show the transition.
        assert "1.0.0" in msg and "1.1.2" in msg
        assert "quodeq version" in msg
        assert "prompts" in msg
        # Opaque hashes never leak — neither 'from' nor 'to'.
        for opaque in ("s3", "s4", "p3", "p4"):
            assert opaque not in msg
        # Rendered in _PROV_FIELDS order: model, standards, prompts, version.
        assert (
            msg.index("model")
            < msg.index("standards")
            < msg.index("prompts")
            < msg.index("quodeq version")
        )


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

    def test_persisted_entry_is_self_describing(self, tmp_path: Path, cache: LocalFileBackend):
        # persist_dispatch_results writes entries that record the content
        # hash they were keyed under and the provenance they were produced
        # under, so reuse across a model/standards boundary is surfaceable.
        files = _write_files(tmp_path / "src", {"a.py": "hello"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work", model="model-1")
        miss_keys = {f: build_cache_key_for_file(config, f, "security") for f in files}

        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
        )

        persist_dispatch_results(
            config, "security", miss_files=files,
            jsonl_path=jsonl, miss_keys=miss_keys, cache=cache,
        )

        entry = cache.get(miss_keys["a.py"])
        assert entry is not None
        assert entry.file_content_hash == hashlib.sha256(b"hello").hexdigest()
        assert entry.provenance["model_id"] == "model-1"
        assert "prompts_hash" in entry.provenance
        assert "standards_hash" in entry.provenance
        assert "quodeq_version" in entry.provenance

    def test_persisted_provenance_folds_project_overrides(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # The persisted standards_hash must be the override-aware value —
        # identical to what classify computes for the same run — or the very
        # next classify would report phantom standards drift.
        from quodeq.analysis.fingerprint import _hash_standards

        src = tmp_path / "src"
        files = _write_files(src, {"a.py": "x"})
        standards_dir = tmp_path / "standards"
        _write_compiled_standards(standards_dir, "security", '{"rule": "v1"}')
        _write_project_overrides(
            src, '{"version": 1, "overrides": {"S-INJ-1": {"max_lines": 60}}}',
        )
        config = _make_config(src, standards_dir=standards_dir, work_dir=tmp_path / "work")
        miss_keys = {f: build_cache_key_for_file(config, f, "security") for f in files}

        jsonl = tmp_path / "work" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(
            json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
        )
        persist_dispatch_results(
            config, "security", miss_files=files,
            jsonl_path=jsonl, miss_keys=miss_keys, cache=cache,
        )

        entry = cache.get(miss_keys["a.py"])
        assert entry is not None
        expected = _hash_standards(standards_dir, "security", src)
        assert entry.provenance["standards_hash"] == expected
        assert entry.provenance["standards_hash"] != _hash_standards(
            standards_dir, "security",
        )

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
