"""persist_dispatch_results: per-file entries written after dispatch, and the classify roundtrip."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quodeq.analysis.cache import LocalFileBackend
from quodeq.analysis.cache._persist_watcher import CachePersistTarget
from quodeq.analysis.cache.dimension_helpers import (
    ClassifyResult,
    build_cache_key_for_file,
    classify_files_via_cache,
    persist_dispatch_results,
)

from ._dimension_helpers_helpers import (
    _hash_inputs,
    _make_config,
    _write_compiled_standards,
    _write_files,
    _write_project_overrides,
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
            config, "security",
            classify=ClassifyResult(misses=files, miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
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
            config, "security",
            classify=ClassifyResult(misses=files, miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
        )

        entry = cache.get(miss_keys["clean.py"])
        assert entry is not None
        assert entry.findings == []

    def test_only_writes_for_miss_files(self, tmp_path: Path, cache: LocalFileBackend):
        # JSONL might contain findings for files that weren't in misses
        # (e.g. carry-forward findings). We only cache entries for the
        # missed files we actually dispatched.
        _write_files(tmp_path / "src", {"a.py": "x", "carried.py": "y"})
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
            config, "security",
            classify=ClassifyResult(misses=["a.py"], miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
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
            config, "security",
            classify=ClassifyResult(misses=files, miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
        )

        entry = cache.get(miss_keys["a.py"])
        assert entry is not None
        assert entry.file_content_hash == hashlib.sha256(b"hello").hexdigest()
        assert entry.provenance["model_id"] == "model-1"
        assert "prompts_hash" in entry.provenance
        assert "standards_hash" in entry.provenance
        assert "quodeq_version" in entry.provenance
        from quodeq.analysis.cache._key_provenance import build_cache_key_struct
        assert entry.params_hash == build_cache_key_struct(config, "a.py", "security").params_hash
        assert entry.cache_format_version == 3

    def test_persisted_provenance_folds_project_overrides(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # The persisted standards_hash must be the override-aware value —
        # identical to what classify computes for the same run — or the very
        # next classify would report phantom standards drift.
        from quodeq.analysis.fingerprint import hash_standards

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
            config, "security",
            classify=ClassifyResult(misses=files, miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
        )

        entry = cache.get(miss_keys["a.py"])
        assert entry is not None
        expected = hash_standards(standards_dir, "security", src)
        assert entry.provenance["standards_hash"] == expected
        assert entry.provenance["standards_hash"] != hash_standards(
            standards_dir, "security",
        )

    def test_handles_missing_jsonl(self, tmp_path: Path, cache: LocalFileBackend):
        _write_files(tmp_path / "src", {"a.py": "x"})
        config = _make_config(tmp_path / "src", work_dir=tmp_path / "work")
        miss_keys = {"a.py": build_cache_key_for_file(config, "a.py", "security")}

        # JSONL doesn't exist (e.g. dispatch failed before writing).
        persist_dispatch_results(
            config, "security",
            classify=ClassifyResult(misses=["a.py"], miss_keys=miss_keys),
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=tmp_path / "work" / "missing.jsonl", cache=cache),
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
            config, "security", classify=first,
            provenance=_hash_inputs(config, "security"),
            target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
        )

        # Second call: cache should be fully populated → all hits. The
        # entries persist_dispatch_results just wrote are unconsolidated
        # (no COMPLETED run has consolidated them yet), so they land in
        # unconsolidated_findings, not cached_findings.
        second = classify_files_via_cache(config, "security", files, cache)
        assert second.misses == []
        assert second.cached_findings == []
        assert {f["file"] for f in second.unconsolidated_findings} == set(files)


def test_persist_dispatch_results_marks_entries_unconsolidated(tmp_path):
    """The periodic-persist watcher path must agree with the synchronous
    cache_writer path: both produce unconsolidated entries."""
    import json as _json

    from quodeq.analysis.cache.dimension_helpers import (
        build_cache_key_for_file,
        persist_dispatch_results,
    )
    from quodeq.analysis.cache.local import LocalFileBackend

    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x")
    config = _make_config(src)

    jsonl = tmp_path / "security_evidence.jsonl"
    jsonl.write_text(
        _json.dumps({"file": "a.py", "line": 1, "t": "violation", "p": "P1"}) + "\n"
        + _json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n"
    )

    cache = LocalFileBackend(root=tmp_path / "cache")
    key = build_cache_key_for_file(config, "a.py", "security")
    persist_dispatch_results(
        config, "security",
        classify=ClassifyResult(misses=["a.py"], miss_keys={"a.py": key}),
        provenance=_hash_inputs(config, "security"),
        target=CachePersistTarget(jsonl_path=jsonl, cache=cache),
    )

    assert cache.get(key).consolidated is False
