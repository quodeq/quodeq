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
# to _process_single_dimension which routes through process_dimension_with_cache,
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
