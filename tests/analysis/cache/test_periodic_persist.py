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
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import LocalFileBackend, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents.jsonl_utils import deduplicate_jsonl
from quodeq.core.evidence.model import Evidence
from tests.analysis.cache.conftest import _CountingCache


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
        def slow_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
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

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(),
            cache=cache, dispatcher=slow_dispatcher, persist_interval_s=0.05,
        )

        # Final state: cache entry exists (final persist after dispatch).
        key = build_cache_key_for_file(config, "a.py", "security")
        entry = cache.get(key)
        assert entry is not None
        assert any(f.get("w") == "found" for f in entry.findings)


class TestHashInputsHoistedOncePerDispatch:
    def test_hash_functions_called_once_not_per_tick(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """standards_hash/params_hash/prompts_hash are dispatch-constant and
        must be computed once at watcher start, not recomputed on every
        persist tick — regression test for the redundant per-tick hashing
        hoisted out of persist_dispatch_results."""
        config = _setup(tmp_path, {"a.py": "x"})
        config = replace(config, standards_dir=tmp_path / "standards")
        from quodeq.core.evidence.model import Evidence

        def slow_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            jsonl.write_text(
                '{"file": "a.py", "line": 1, "t": "violation", "w": "found"}\n'
                + '{"_marker": "file_done", "file": "a.py", "status": "ok"}\n'
            )
            time.sleep(0.3)  # several persist ticks at the tiny interval below
            return Evidence(
                repository="", language="python", date="2026-01-01",
                source_file_count=1, files_read=1, coverage_pct=100.0,
                principles={},
            )

        mock_hash_standards = MagicMock(return_value="std-hash")
        mock_params_state = MagicMock(return_value=("params-hash", {}))
        mock_hash_prompts = MagicMock(return_value="prompts-hash")

        with (
            patch(
                "quodeq.analysis.cache._persist_watcher._hash_standards",
                mock_hash_standards,
            ),
            patch(
                "quodeq.analysis.cache._persist_watcher.dimension_params_state",
                mock_params_state,
            ),
            patch(
                "quodeq.analysis.cache._persist_watcher._hash_prompts_combined",
                mock_hash_prompts,
            ),
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache, dispatcher=slow_dispatcher, persist_interval_s=0.05,
            )

        # Multiple ticks (~0.3s / 0.05s interval) plus the final persist all
        # reuse the same precomputed values — one call each for the dispatch.
        assert mock_hash_standards.call_count == 1
        assert mock_params_state.call_count == 1
        assert mock_hash_prompts.call_count == 1


class TestWatcherSurvivesDispatchException:
    def test_dispatch_raises_orphan_findings_not_cached(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """If the dispatch raises without emitting a file_done=ok marker, the
        file must NOT be cached — the worker crashed mid-file so we can't trust
        the findings are complete. The next run will re-dispatch."""
        config = _setup(tmp_path, {"a.py": "x"})

        def crashing_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
            jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            # Write partial findings with no ok marker (worker died mid-file).
            jsonl.write_text(
                '{"file": "a.py", "line": 1, "t": "violation", "w": "completed"}\n'
            )
            raise RuntimeError("simulated cancel")

        with pytest.raises(RuntimeError, match="simulated cancel"):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(),
                cache=cache, dispatcher=crashing_dispatcher, persist_interval_s=60.0,
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


# ============================================================
# Incremental ticks and the final full re-read
# ============================================================

_FINDING_A = '{"file": "a.py", "line": 1, "t": "violation", "w": "found"}\n'
_OK_A = '{"_marker": "file_done", "file": "a.py", "status": "ok"}\n'


class _FirstPutCache(_CountingCache):
    """Counting cache that signals its first put and can swallow it, the way
    LocalFileBackend.put does on OSError (logs, returns None, no entry)."""

    def __init__(self, inner: LocalFileBackend, *, swallow_first: bool = False) -> None:
        super().__init__(inner)
        self.first_put = threading.Event()
        self._swallow_first = swallow_first

    def put(self, key, entry) -> None:
        self.put_count += 1
        if not (self._swallow_first and self.put_count == 1):
            self._inner.put(key, entry)
        self.first_put.set()


def _dispatch_after_first_put(text: str, first_put: threading.Event, after_tick=None):
    """Dispatcher that writes *text*, waits for a watcher tick to put once,
    runs *after_tick*(jsonl) (the pool's own post-dispatch work), returns."""

    def dispatch(cfg, dim_id, idx, ctx, callbacks, **_):
        jsonl = cfg.work_dir / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.write_text(text)
        assert first_put.wait(timeout=5.0), "no periodic tick put anything"
        if after_tick is not None:
            after_tick(jsonl)
        return Evidence(
            repository="", language="python", date="2026-01-01",
            source_file_count=1, files_read=1, coverage_pct=100.0, principles={},
        )

    return dispatch


class TestTicksAreIncremental:
    def test_unchanged_ok_file_is_not_re_put_by_later_ticks(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Every tick used to re-read the whole JSONL and re-put every ok
        file. With one DispatchJsonlState per dispatch, later ticks skip a
        file whose lines have not changed. Only the final persist, a
        deliberate full re-read, writes it again: exactly two puts however
        many ticks run between the first put and the stop signal."""
        config = _setup(tmp_path, {"a.py": "x"})
        counting = _FirstPutCache(cache)

        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=counting,
            dispatcher=_dispatch_after_first_put(_FINDING_A + _OK_A, counting.first_put),
            persist_interval_s=0.05,
        )

        assert counting.put_count == 2
        key = build_cache_key_for_file(config, "a.py", "security")
        assert cache.get(key) is not None


class TestFinalPersistIsFullReread:
    def _run(self, tmp_path, cache, text, *, swallow_first=False, after_tick=None):
        config = _setup(tmp_path, {"a.py": "x"})
        wrapped = _FirstPutCache(cache, swallow_first=swallow_first)
        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=wrapped,
            dispatcher=_dispatch_after_first_put(text, wrapped.first_put, after_tick),
            persist_interval_s=0.05,
        )
        return cache.get(build_cache_key_for_file(config, "a.py", "security"))

    def test_put_that_failed_silently_during_a_tick_lands_at_final_persist(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """LocalFileBackend.put swallows OSError, so a tick cannot tell a
        failed write from a good one and clears dirty either way. The final
        persist must not trust that bookkeeping: it re-reads from byte 0 and
        re-puts every ok file."""
        entry = self._run(tmp_path, cache, _FINDING_A + _OK_A, swallow_first=True)
        assert entry is not None
        assert any(f.get("w") == "found" for f in entry.findings)

    def test_dedup_rewrite_after_last_tick_is_reflected(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """The dispatcher runs deduplicate_jsonl in place before the watcher
        is joined; the final persist sees the deduplicated file."""
        entry = self._run(
            tmp_path, cache, _FINDING_A + _FINDING_A + _OK_A, after_tick=deduplicate_jsonl,
        )
        assert entry is not None
        assert len(entry.findings) == 1

    def test_rewrite_invisible_to_the_tail_guard_is_reflected(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """The incremental guard compares only the 512 bytes before the
        offset, so a rewrite that leaves them alone (a same-length change in
        an earlier line) is invisible to a tick. The final persist must not
        depend on the guard."""
        padding = '{"file": "a.py", "line": 2, "t": "violation", "w": "%s"}\n' % ("p" * 600)
        text = _FINDING_A + padding + _OK_A

        def rewrite(jsonl: Path) -> None:
            jsonl.write_text(text.replace('"w": "found"', '"w": "later"'))

        entry = self._run(tmp_path, cache, text, after_tick=rewrite)
        assert entry is not None
        ws = {f.get("w") for f in entry.findings}
        assert "later" in ws
        assert "found" not in ws
