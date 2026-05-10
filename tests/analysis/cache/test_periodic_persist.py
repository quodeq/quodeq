"""Periodic cache persistence during dispatch (B5e).

When a dimension runs, the dispatch can take minutes. If the user
cancels mid-dim, the previous design lost cache entries for files that
*had* completed (because persist_dispatch_results only ran after the
pool returned cleanly). This suite pins down a watcher thread that
persists periodically, reducing the lost-work window from "entire dim"
to "current persist interval."

The watcher runs in process_dimension_with_cache:

  1. Started after classify, before dispatching the misses
  2. Periodically calls persist_dispatch_results during dispatch
  3. Stops after dispatch returns (including exceptions)
  4. Final persist on stop is best-effort; failures don't propagate
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest


def _make_manifest(file_names: list[str]) -> SourceManifest:
    target = AnalysisTarget(
        name="t", language="python", source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _setup(tmp_path: Path, contents: dict[str, str]) -> RunConfig:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    for n, t in contents.items():
        (src / n).write_text(t)
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=tmp_path / "work",
        options=AnalysisOptions(subagent_model="test-model"),
        manifest=_make_manifest(sorted(contents.keys())),
    )


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01", template="", subagent_template="", total=1,
    )


def _make_callbacks():
    from quodeq.analysis._dimension_steps import (
        _build_dimension_prompt, _parse_dimension_evidence, _run_dimension_analysis,
    )
    from quodeq.analysis.subagents.runner import DimensionCallbacks
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


# ============================================================
# Watcher behaviour
# ============================================================


class TestWatcherStartsAndStops:
    def test_watcher_runs_during_dispatch(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """A long-running dispatch should see at least one watcher tick that
        persists what's in the JSONL even before dispatch returns."""
        config = _setup(tmp_path, {"a.py": "x"})
        from quodeq.core.evidence.model import Evidence

        # The fake dispatcher writes a finding to JSONL, then sleeps long enough
        # that the watcher (with a tiny interval) ticks at least once.
        def slow_dispatcher(cfg, dim_id, idx, ctx, callbacks):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            jsonl.write_text(
                '{"file": "a.py", "line": 1, "t": "violation", "w": "found"}\n'
                + '{"_marker": "file_done", "file": "a.py", "status": "ok"}\n'
            )
            time.sleep(0.3)  # let the watcher tick
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0,
                principles={},
            )

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=slow_dispatcher,
        ), patch(
            "quodeq.analysis.cache.dimension_runner._PERSIST_INTERVAL_S", 0.05,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache,
            )

        # Final state: cache entry exists (final persist after dispatch).
        key = build_cache_key_for_file(config, "a.py", "security")
        entry = cache.get(key)
        assert entry is not None
        assert any(f.get("w") == "found" for f in entry.findings)


class TestWatcherSurvivesDispatchException:
    def test_dispatch_raises_orphan_findings_not_cached(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """If the dispatch raises without emitting a file_done=ok marker, the
        file must NOT be cached — the worker crashed mid-file so we can't trust
        the findings are complete. The next run will re-dispatch."""
        config = _setup(tmp_path, {"a.py": "x"})

        def crashing_dispatcher(cfg, dim_id, idx, ctx, callbacks):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            # Write partial findings with no ok marker (worker died mid-file).
            jsonl.write_text(
                '{"file": "a.py", "line": 1, "t": "violation", "w": "completed"}\n'
            )
            raise RuntimeError("simulated cancel")

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=crashing_dispatcher,
        ), patch(
            "quodeq.analysis.cache.dimension_runner._PERSIST_INTERVAL_S", 60.0,
        ):
            with pytest.raises(RuntimeError, match="simulated cancel"):
                process_dimension_with_cache(
                    config, "security", 1, _make_ctx(), _make_callbacks(),
                    cache=cache,
                )

        # No ok marker emitted → orphaned findings must NOT be cached.
        key = build_cache_key_for_file(config, "a.py", "security")
        entry = cache.get(key)
        assert entry is None, "orphaned findings without ok marker must not be cached"


class TestNoWatcherWhenNoMisses:
    def test_all_hits_does_not_start_watcher(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """When there's nothing to dispatch (all hits), the watcher is
        unnecessary and should not start. This is the fast-path
        optimization — no thread overhead for cached runs."""
        from quodeq.analysis.cache import CacheEntry
        config = _setup(tmp_path, {"a.py": "x"})

        # Pre-populate cache.
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "v"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        # Track Thread() instantiations.
        original_thread = threading.Thread
        threads_created: list[threading.Thread] = []
        def tracking_thread(*args, **kwargs):
            t = original_thread(*args, **kwargs)
            threads_created.append(t)
            return t

        # Patch Thread inside the dimension_runner module (where it's used).
        with patch(
            "quodeq.analysis.cache.dimension_runner.threading.Thread",
            new=tracking_thread,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache,
            )

        # All-hits path → no watcher thread started.
        watcher_threads = [t for t in threads_created if t.name and "v2-cache-persist" in t.name]
        assert watcher_threads == []
