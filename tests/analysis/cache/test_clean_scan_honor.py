"""Clean-scan honoring at the V2 cache layer.

When the user requests a clean scan (config.options.incremental=False),
V2 must not serve cache hits — that's the whole point of the flag. But
fresh dispatch results SHOULD still be written to the cache so future
incremental runs benefit from the refresh.

Three boundaries are tested here:

  1. classify_files_via_cache(bypass_reads=True): every file goes to
     misses regardless of cache state. The miss_keys map is still
     populated so persist_dispatch_results can write entries.

  2. _try_v2_full_hit (orchestrator-level fast-path): returns None
     when incremental=False so V1's clean-scan path takes over.

  3. process_dimension_with_cache (dispatch-level): bypasses cache
     reads when incremental=False, dispatches all files, writes
     fresh results to the cache.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import (
    CacheEntry,
    LocalFileBackend,
    build_cache_key_for_file,
    classify_files_via_cache,
)
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


# ============================================================
# Shared fixtures
# ============================================================


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _setup(
    tmp_path: Path, contents: dict[str, str], *, incremental: bool = True,
) -> tuple[RunConfig, Path]:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for name, text in contents.items():
        (src / name).write_text(text)
    config = RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=tmp_path / "work",
        options=AnalysisOptions(subagent_model="test-model", incremental=incremental),
        manifest=_make_manifest(sorted(contents.keys())),
    )
    return config, src


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01", template="", subagent_template="", total=1,
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache_v2")


def _populate_cache(cache, config, dim, files: list[str]) -> None:
    for f in files:
        key = build_cache_key_for_file(config, f, dim)
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": f, "line": 1, "t": "violation", "w": f"cached-{f}"}],
            files_read=1, file_path=f, dimension=dim, model_id="test-model",
        ))


# ============================================================
# 1. classify_files_via_cache(bypass_reads=True)
# ============================================================


class TestClassifyBypassReads:
    def test_bypass_reads_all_miss_despite_full_cache(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config, _ = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        _populate_cache(cache, config, "security", ["a.py", "b.py"])

        result = classify_files_via_cache(
            config, "security", ["a.py", "b.py"], cache,
            bypass_reads=True,
        )
        assert result.cached_findings == []
        assert sorted(result.misses) == ["a.py", "b.py"]
        # miss_keys must still be populated so writeback works.
        assert set(result.miss_keys.keys()) == {"a.py", "b.py"}

    def test_default_reads_normally(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Sanity: bypass_reads defaults to False and existing behaviour holds."""
        config, _ = _setup(tmp_path, {"a.py": "x"})
        _populate_cache(cache, config, "security", ["a.py"])

        result = classify_files_via_cache(config, "security", ["a.py"], cache)
        assert result.misses == []
        assert len(result.cached_findings) == 1


# Removed TestOrchestratorFastPathHonorsCleanScan: the orchestrator-level
# _try_v2_full_hit no longer exists. After B6 the orchestrator delegates
# to DimensionRunner.run which routes through process_dimension_with_cache,
# and clean-scan honoring is verified at that layer (TestDispatchBypassesCacheOnCleanScan).


# ============================================================
# 3. process_dimension_with_cache honors incremental=False
# ============================================================


class TestDispatchBypassesCacheOnCleanScan:
    def test_clean_scan_dispatches_all_files_despite_full_cache(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config, _ = _setup(tmp_path, {"a.py": "x", "b.py": "y"}, incremental=False)
        _populate_cache(cache, config, "security", ["a.py", "b.py"])

        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
        from quodeq.core.evidence.model import Evidence

        dispatched_files: list[str] = []
        def fake_dispatcher(cfg, dim_id, idx, ctx, callbacks):
            files = sorted(cfg.options.incremental_file_filter or set())
            dispatched_files.extend(files)
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                for f in files:
                    out.write(json.dumps({
                        "file": f, "line": 1, "t": "violation", "w": f"fresh-{f}",
                    }) + "\n")
                    out.write(json.dumps({
                        "_marker": "file_done", "file": f, "status": "ok",
                    }) + "\n")
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=len(files), files_read=len(files),
                coverage_pct=100.0, principles={},
            )

        from quodeq.analysis._dimension_steps import (
            _build_dimension_prompt, _parse_dimension_evidence, _run_dimension_analysis,
        )
        from quodeq.analysis.subagents.runner import DimensionCallbacks
        callbacks = DimensionCallbacks(
            build_prompt=_build_dimension_prompt,
            run_analysis=_run_dimension_analysis,
            parse_evidence=_parse_dimension_evidence,
        )

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), callbacks, cache=cache,
            )

        # All files re-dispatched, NOT served from cache.
        assert sorted(dispatched_files) == ["a.py", "b.py"]

    def test_clean_scan_still_writes_fresh_results_to_cache(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Clean scan bypasses reads but writes — the cache stays current."""
        config, _ = _setup(tmp_path, {"a.py": "x"}, incremental=False)
        # Pre-populate with a stale entry that should be overwritten.
        old_key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(old_key, CacheEntry(
            key=old_key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "stale"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
        from quodeq.core.evidence.model import Evidence

        def fake_dispatcher(cfg, dim_id, idx, ctx, callbacks):
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "file": "a.py", "line": 1, "t": "violation", "w": "fresh",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "a.py", "status": "ok",
                }) + "\n")
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0,
                principles={},
            )

        from quodeq.analysis._dimension_steps import (
            _build_dimension_prompt, _parse_dimension_evidence, _run_dimension_analysis,
        )
        from quodeq.analysis.subagents.runner import DimensionCallbacks
        callbacks = DimensionCallbacks(
            build_prompt=_build_dimension_prompt,
            run_analysis=_run_dimension_analysis,
            parse_evidence=_parse_dimension_evidence,
        )

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), callbacks, cache=cache,
            )

        # Cache entry was overwritten with the fresh dispatch result.
        entry = cache.get(old_key)
        assert entry is not None
        assert any(f.get("w") == "fresh" for f in entry.findings)
        assert all(f.get("w") != "stale" for f in entry.findings)


# ============================================================
# Cache invalidation on clean scan (the "I want fresh" guarantee)
# ============================================================
#
# Background: prior to this fix, a clean scan only set bypass_reads=True
# (so the in-flight run ignored cache hits) but left existing entries
# alone. If the user cancelled the clean scan mid-flight and re-ran
# without --clean, the prior entries the user wanted refreshed were
# still hits, producing the surprising "instant complete" behaviour.
#
# Now: clean scan deletes the (file, dim) cache entries up front. A
# completing clean scan repopulates them; a cancelled clean scan leaves
# the cache holding only what THIS run finished, never ghosts from
# before.


class TestCleanScanInvalidates:
    def test_clean_scan_deletes_entries_for_this_dim_files(
        self, tmp_path: Path, cache,
    ):
        """Pre-populated entries are gone after process_dimension_with_cache
        runs with incremental=False, even if the dispatch is short-circuited."""
        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache

        config, src = _setup(
            tmp_path, {"a.py": "x", "b.py": "y"}, incremental=False,
        )
        _populate_cache(cache, config, "security", ["a.py", "b.py"])

        # Sanity: entries exist before.
        for f in ("a.py", "b.py"):
            assert cache.get(build_cache_key_for_file(config, f, "security")) is not None

        from quodeq.core.evidence.model import Evidence
        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks):
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            # Worker emits a marker for a.py only -- b.py is "abandoned"
            # mid-flight (simulating a cancel after a finished).
            with jsonl.open("w") as out:
                out.write(json.dumps({"file": "a.py", "line": 1, "t": "violation", "w": "fresh-a"}) + "\n")
                out.write(json.dumps({"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n")
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=2, files_read=1, coverage_pct=50.0, principles={},
            )

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatch,
        ):
            from quodeq.analysis.subagents.runner import DimensionCallbacks
            from quodeq.analysis._dimension_steps import (
                _build_dimension_prompt, _parse_dimension_evidence, _run_dimension_analysis,
            )
            callbacks = DimensionCallbacks(
                build_prompt=_build_dimension_prompt,
                run_analysis=_run_dimension_analysis,
                parse_evidence=_parse_dimension_evidence,
            )
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), callbacks, cache=cache,
            )

        # a.py: re-dispatched, ok marker, repopulated under same key with FRESH content.
        a_entry = cache.get(build_cache_key_for_file(config, "a.py", "security"))
        assert a_entry is not None, "a.py should be re-cached after clean-scan"
        assert any(f.get("w") == "fresh-a" for f in a_entry.findings)
        assert all(f.get("w") != "cached-a.py" for f in a_entry.findings), (
            "stale pre-clean-scan finding leaked through -- the wipe-then-rewrite contract is broken"
        )

        # b.py: invalidated up front, never got an ok marker -- entry is GONE.
        b_entry = cache.get(build_cache_key_for_file(config, "b.py", "security"))
        assert b_entry is None, (
            "stale b.py entry survived a clean-scan that never re-completed it -- "
            "next non-clean run would short-circuit on the ghost entry"
        )

    def test_incremental_run_does_not_invalidate(
        self, tmp_path: Path, cache,
    ):
        """Sanity: invalidation is gated on bypass_reads. A normal
        incremental run that happens to find no hits MUST NOT delete
        anything."""
        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache

        config, src = _setup(
            tmp_path, {"a.py": "x"}, incremental=True,
        )
        _populate_cache(cache, config, "security", ["a.py"])
        key_before = build_cache_key_for_file(config, "a.py", "security")
        entry_before = cache.get(key_before)
        assert entry_before is not None

        from quodeq.core.evidence.model import Evidence
        def noop_dispatch(cfg, dim_id, idx, ctx, callbacks):
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0, principles={},
            )

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=noop_dispatch,
        ):
            from quodeq.analysis.subagents.runner import DimensionCallbacks
            from quodeq.analysis._dimension_steps import (
                _build_dimension_prompt, _parse_dimension_evidence, _run_dimension_analysis,
            )
            callbacks = DimensionCallbacks(
                build_prompt=_build_dimension_prompt,
                run_analysis=_run_dimension_analysis,
                parse_evidence=_parse_dimension_evidence,
            )
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), callbacks, cache=cache,
            )

        # All-hits path; entry survives untouched.
        entry_after = cache.get(key_before)
        assert entry_after is not None
        assert any(f.get("w") == "cached-a.py" for f in entry_after.findings)
