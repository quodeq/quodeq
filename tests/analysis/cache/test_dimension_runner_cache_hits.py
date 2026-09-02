"""process_dimension_with_cache — hit/miss classification.

Split from test_dimension_runner.py: all-hits short-circuits dispatch
entirely, all-misses dispatches with the original file set, and partial
dispatches with file filter restricted to misses. files_read accounting
is split out further into test_dimension_runner_accounting.py. Shared
scaffolding (FakeDispatcher, _setup, the ``cache`` fixture, etc.) lives
in tests/analysis/cache/conftest.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

from quodeq.analysis.cache import CacheEntry, build_cache_key_for_file
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from tests.analysis.cache.conftest import (
    FakeDispatcher,
    _ListHandler,
    _make_callbacks,
    _make_ctx,
    _setup,
)


class TestAllHits:
    def test_all_hits_skip_dispatch_entirely(self, tmp_path: Path, cache):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Pre-populate cache for both files.
        for f, finding_text in [("a.py", "a-cached"), ("b.py", "b-cached")]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1,
                findings=[{"file": f, "line": 1, "t": "violation", "w": finding_text}],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        dispatcher = FakeDispatcher(src)
        ev = process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        # No dispatch happened.
        assert dispatcher.calls == []
        assert ev is not None

        # Final JSONL contains exactly the cached findings.
        jsonl = (tmp_path / "work" / "security_evidence.jsonl").read_text()
        lines = [json.loads(l) for l in jsonl.splitlines() if l.strip()]
        assert {l["w"] for l in lines} == {"a-cached", "b-cached"}


class TestProvenanceSurfacing:
    def test_classify_log_names_model_drift_on_all_hits(
        self, tmp_path: Path, cache,
    ):
        # Reuse across a model change must never be silent: the per-dim
        # classify log line surfaces that reused findings predate the
        # current model.
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        for f in ["a.py", "b.py"]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=3,
                findings=[{"file": f, "line": 1, "t": "violation", "w": f"{f}-cached"}],
                files_read=1, file_path=f, dimension="security",
                model_id="old-model",
                provenance={
                    "model_id": "old-model", "standards_hash": "",
                    "prompts_hash": "", "quodeq_version": "",
                },
            ))

        handler = _ListHandler()
        logger = logging.getLogger("quodeq.analysis.cache.dimension_runner")
        logger.addHandler(handler)
        dispatcher = FakeDispatcher(src)
        try:
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
                dispatcher=dispatcher,
            )
        finally:
            logger.removeHandler(handler)

        assert dispatcher.calls == []
        text = "\n".join(handler.messages)
        assert "model" in text.lower()
        assert "old-model" in text  # the model the reused findings predate


class TestModelSwitchReuse:
    def test_second_run_with_new_model_is_all_hits(
        self, tmp_path: Path, cache,
    ):
        # The headline cost-first behavior: run a dimension on model A, then
        # the SAME code on model B. The second run reuses every cached
        # finding with zero re-dispatch, and the entries still record model A
        # as their provenance so the drift is surfaceable.
        config_a, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        # config_a model is "test-model" (the _make_config default).

        d1 = FakeDispatcher(src)
        process_dimension_with_cache(
            config_a, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=d1,
        )
        assert len(d1.calls) == 1  # cold cache -> dispatched the misses

        # Same project, different model.
        config_b = replace(
            config_a,
            options=replace(config_a.options, subagent_model="other-model"),
        )
        d2 = FakeDispatcher(src)
        handler = _ListHandler()
        logger = logging.getLogger("quodeq.analysis.cache.dimension_runner")
        logger.addHandler(handler)
        try:
            ev = process_dimension_with_cache(
                config_b, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
                dispatcher=d2,
            )
        finally:
            logger.removeHandler(handler)

        # All hits despite the model change: no re-dispatch.
        assert d2.calls == []
        assert ev is not None

        # The cache key is identical across the model switch, and the entry
        # still remembers the model that produced it.
        key = build_cache_key_for_file(config_b, "a.py", "security")
        assert key == build_cache_key_for_file(config_a, "a.py", "security")
        entry = cache.get(key)
        assert entry is not None
        assert entry.provenance["model_id"] == "test-model"

        # End-to-end: the provenance written by run 1's persist is read back
        # by run 2's classify and surfaced on the log, naming the model the
        # reused findings predate. This pins the persist -> classify ->
        # format_provenance_drift seam that the unit tests stub.
        text = "\n".join(handler.messages)
        assert "model" in text.lower()
        assert "test-model" in text


class TestAllMisses:
    def test_cold_cache_dispatches_all_files(self, tmp_path: Path, cache):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        dispatcher = FakeDispatcher(src)
        ev = process_dimension_with_cache(
            config, "security", idx=1, ctx=_make_ctx(),
            callbacks=_make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        # Dispatch happened with all files (file filter == all source files).
        assert len(dispatcher.calls) == 1
        dispatched = dispatcher.calls[0].options.incremental_file_filter
        assert dispatched == {"a.py", "b.py"}
        assert ev is not None

        # Cache entries written for both files after dispatch.
        for f in ["a.py", "b.py"]:
            key = build_cache_key_for_file(config, f, "security")
            entry = cache.get(key)
            assert entry is not None, f"no cache entry for {f}"
            assert entry.findings, f"empty findings for {f}"

    def test_second_run_after_cold_is_all_hits(self, tmp_path: Path, cache):
        """Sanity end-to-end: cold run populates cache, second run hits."""
        config, src = _setup(tmp_path, {"a.py": "x"})

        dispatcher = FakeDispatcher(src)
        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )
        # Run 2 — should not dispatch.
        dispatcher.calls.clear()
        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )
        assert dispatcher.calls == []


class TestPartialHits:
    def test_dispatches_only_misses(self, tmp_path: Path, cache):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})

        # Pre-populate b.py only.
        key_b = build_cache_key_for_file(config, "b.py", "security")
        cache.put(key_b, CacheEntry(
            key=key_b, schema_version=1,
            findings=[{"file": "b.py", "line": 1, "t": "violation", "w": "b-cached"}],
            files_read=1, file_path="b.py", dimension="security",
            model_id="test-model",
        ))

        dispatcher = FakeDispatcher(src)
        ev = process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )

        # Dispatcher saw only the misses.
        assert len(dispatcher.calls) == 1
        dispatched = dispatcher.calls[0].options.incremental_file_filter
        assert dispatched == {"a.py", "c.py"}
        assert ev is not None

        # Final JSONL combines miss findings + cached findings.
        jsonl = (tmp_path / "work" / "security_evidence.jsonl").read_text()
        lines = [json.loads(l) for l in jsonl.splitlines() if l.strip()]
        files_in_jsonl = {l["file"] for l in lines}
        assert files_in_jsonl == {"a.py", "b.py", "c.py"}

        # b.py's cached finding survived; a.py and c.py were freshly dispatched.
        b_findings = [l for l in lines if l["file"] == "b.py"]
        assert any(l["w"] == "b-cached" for l in b_findings)


class TestDispatchFailure:
    def test_dispatcher_returns_none_no_cache_writes(self, tmp_path: Path, cache):
        config, src = _setup(tmp_path, {"a.py": "x"})

        def failing_dispatcher(*args, **kwargs):
            return None

        ev = process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            dispatcher=failing_dispatcher,
        )
        assert ev is None

        # No cache entry was written for the failed dispatch.
        key = build_cache_key_for_file(config, "a.py", "security")
        assert cache.get(key) is None


class TestNoSourceFiles:
    def test_falls_through_to_dispatcher_when_no_files(self, tmp_path: Path, cache):
        # Empty src — the cache layer can't classify, defer to dispatcher.
        config, src = _setup(tmp_path, {})

        dispatcher = FakeDispatcher(src)
        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            dispatcher=dispatcher,
        )
        # Dispatcher was called (even with no files — same as V1 behaviour).
        assert len(dispatcher.calls) == 1

