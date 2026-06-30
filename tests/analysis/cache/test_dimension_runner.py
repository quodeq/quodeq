"""process_dimension_with_cache — V2 dimension processor.

Composes the B4 helpers (classify, persist, key) with the existing
dispatcher boundary (process_dimension_with_subagents) into a
cache-aware dimension runner.

These tests pin down the orchestration:

  - all-hits short-circuits dispatch entirely
  - all-misses dispatches with the original file set
  - partial dispatches with file filter restricted to misses
  - missed-file findings are persisted to cache after dispatch
  - cached findings are merged into final Evidence
  - dispatcher returning None propagates without writing cache entries

The dispatcher is patched at the boundary
(process_dimension_with_subagents) so we don't need a real subagent
pool. The runner's behaviour is fully observable through the cache
state and the dispatcher call recorder.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.analysis._types import AnalysisOptions, RunConfig, _AnalysisContext
from quodeq.analysis.cache import (
    CacheEntry,
    LocalFileBackend,
    build_cache_key_for_file,
)
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from quodeq.analysis.cache._failure_streak import CircuitBreakerError
from quodeq.analysis.manifest_models import AnalysisTarget, SourceManifest
from quodeq.analysis.subagents.runner import DimensionCallbacks
from quodeq.core.evidence.model import Evidence


# ============================================================
# Test scaffolding
# ============================================================


def _make_manifest(file_names: list[str]) -> SourceManifest:
    """Manifest with a single Python target listing the given files."""
    target = AnalysisTarget(
        name="test", language="python",
        source_files=sorted(file_names),
        total_files=len(file_names),
        language_stats={"py": len(file_names)},
    )
    return SourceManifest(targets=[target], total_files=len(file_names))


def _make_config(
    src: Path, *, work_dir: Path | None = None,
    file_names: list[str] | None = None,
) -> RunConfig:
    return RunConfig(
        src=src, language="python", standards_dir=None,
        work_dir=work_dir or src,
        options=AnalysisOptions(subagent_model="test-model"),
        manifest=_make_manifest(file_names or []) if file_names is not None else None,
    )


def _write_files(root: Path, contents: dict[str, str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _setup(
    tmp_path: Path, contents: dict[str, str] | None = None,
) -> tuple[RunConfig, Path]:
    """Create files + a config wired with a manifest. Returns (config, src)."""
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    if contents:
        _write_files(src, contents)
    config = _make_config(
        src, work_dir=tmp_path / "work",
        file_names=sorted(contents.keys()) if contents else [],
    )
    return config, src


def _make_ctx() -> _AnalysisContext:
    from quodeq.analysis._dimensions import DimensionsConfig
    return _AnalysisContext(
        dimensions_data=DimensionsConfig(dimensions={}),
        date_str="2026-01-01",
        template="",
        subagent_template="",
        total=1,
    )


def _make_callbacks() -> DimensionCallbacks:
    """Real callbacks aren't needed when the dispatcher boundary is mocked."""
    from quodeq.analysis._dimension_steps import (
        _build_dimension_prompt,
        _parse_dimension_evidence,
        _run_dimension_analysis,
    )
    return DimensionCallbacks(
        build_prompt=_build_dimension_prompt,
        run_analysis=_run_dimension_analysis,
        parse_evidence=_parse_dimension_evidence,
    )


class FakeDispatcher:
    """Stand-in for process_dimension_with_subagents that writes a JSONL
    and returns a synthetic Evidence — same contract as the real thing."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.calls: list[RunConfig] = []

    def __call__(
        self, config: RunConfig, dim_id: str, idx: int, ctx, callbacks,
    ) -> Evidence | None:
        self.calls.append(config)
        # Mirror what the real dispatcher does: write findings to JSONL
        # for each file in the (filtered) file list. Findings are
        # deterministic per file so we can assert on them.
        evidence_dir = config.work_dir or config.src
        jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        files_to_dispatch = (
            sorted(config.options.incremental_file_filter)
            if config.options.incremental_file_filter
            else self._all_source_files()
        )
        with jsonl.open("a") as out:
            for f in files_to_dispatch:
                out.write(json.dumps({
                    "file": f, "line": 1, "t": "violation", "w": f"v-{f}",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": f, "status": "ok",
                }) + "\n")
        return _make_dummy_evidence(files_read=len(files_to_dispatch))

    def _all_source_files(self) -> list[str]:
        return sorted(
            str(p.relative_to(self.project_root))
            for p in self.project_root.rglob("*.py")
        )


def _make_dummy_evidence(*, files_read: int) -> Evidence:
    """Minimal Evidence shape — the V2 runner re-parses from JSONL anyway,
    so the dispatcher's exact return value isn't what matters."""
    return Evidence(
        repository="", language="python", date="2026-01-01",
        source_file_count=files_read, files_read=files_read,
        coverage_pct=100.0, principles={},
    )


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


# ============================================================
# Behavioural tests
# ============================================================


class TestAllHits:
    def test_all_hits_skip_dispatch_entirely(self, tmp_path: Path, cache: LocalFileBackend):
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
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        # No dispatch happened.
        assert dispatcher.calls == []
        assert ev is not None

        # Final JSONL contains exactly the cached findings.
        jsonl = (tmp_path / "work" / "security_evidence.jsonl").read_text()
        lines = [json.loads(l) for l in jsonl.splitlines() if l.strip()]
        assert {l["w"] for l in lines} == {"a-cached", "b-cached"}


class _ListHandler(logging.Handler):
    """Capture log messages off a specific logger. The ``quodeq`` logger sets
    propagate=False, so pytest's caplog (root) can't see these records — we
    attach directly to the module logger instead."""

    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


class TestProvenanceSurfacing:
    def test_classify_log_names_model_drift_on_all_hits(
        self, tmp_path: Path, cache: LocalFileBackend,
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
            with patch(
                "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
                new=dispatcher,
            ):
                process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
                )
        finally:
            logger.removeHandler(handler)

        assert dispatcher.calls == []
        text = "\n".join(handler.messages)
        assert "model" in text.lower()
        assert "old-model" in text  # the model the reused findings predate


class TestModelSwitchReuse:
    def test_second_run_with_new_model_is_all_hits(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # The headline cost-first behavior: run a dimension on model A, then
        # the SAME code on model B. The second run reuses every cached
        # finding with zero re-dispatch, and the entries still record model A
        # as their provenance so the drift is surfaceable.
        config_a, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})
        # config_a model is "test-model" (the _make_config default).

        d1 = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=d1,
        ):
            process_dimension_with_cache(
                config_a, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
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
            with patch(
                "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
                new=d2,
            ):
                ev = process_dimension_with_cache(
                    config_b, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
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


class TestGcWiring:
    def test_default_backend_open_collects_legacy_entries(
        self, tmp_path: Path, monkeypatch,
    ):
        # When no cache is injected (the production path), opening the default
        # backend runs the one-time GC, reclaiming schema<3 entries. Sandbox
        # the cache root via env so we never touch the real ~/.quodeq cache.
        from quodeq.analysis.cache.local import default_cache_root

        monkeypatch.setenv("QUODEQ_CACHE_ROOT", str(tmp_path / "qroot"))
        results_root = default_cache_root()
        legacy_dir = results_root / "aa" / ("0" * 62)
        legacy_dir.mkdir(parents=True, exist_ok=True)
        (legacy_dir / "entry.json").write_text(json.dumps({
            "key": "aa" + "0" * 62, "schema_version": 2, "findings": [],
            "files_read": 1, "file_path": "old.py", "dimension": "security",
            "model_id": "m",
        }))

        config, src = _setup(tmp_path, {"a.py": "x"})
        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            # cache=None -> production default-backend path -> GC fires.
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=None,
            )

        assert not (legacy_dir / "entry.json").exists()


class TestAllMisses:
    def test_cold_cache_dispatches_all_files(self, tmp_path: Path, cache: LocalFileBackend):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
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

    def test_second_run_after_cold_is_all_hits(self, tmp_path: Path, cache: LocalFileBackend):
        """Sanity end-to-end: cold run populates cache, second run hits."""
        config, src = _setup(tmp_path, {"a.py": "x"})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
            # Run 2 — should not dispatch.
            dispatcher.calls.clear()
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
        assert dispatcher.calls == []


class TestPartialHits:
    def test_dispatches_only_misses(self, tmp_path: Path, cache: LocalFileBackend):
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
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
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
    def test_dispatcher_returns_none_no_cache_writes(self, tmp_path: Path, cache: LocalFileBackend):
        config, src = _setup(tmp_path, {"a.py": "x"})

        def failing_dispatcher(*args, **kwargs):
            return None

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=failing_dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
        assert ev is None

        # No cache entry was written for the failed dispatch.
        key = build_cache_key_for_file(config, "a.py", "security")
        assert cache.get(key) is None


class TestNoSourceFiles:
    def test_falls_through_to_dispatcher_when_no_files(self, tmp_path: Path, cache: LocalFileBackend):
        # Empty src — the cache layer can't classify, defer to dispatcher.
        config, src = _setup(tmp_path, {})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
            )
        # Dispatcher was called (even with no files — same as V1 behaviour).
        assert len(dispatcher.calls) == 1


# ============================================================
# Wiring smoke test
# ============================================================


class TestWiring:
    def test_dimension_runner_routes_to_cache_runner(
        self, tmp_path: Path,
    ):
        """V2 is the canonical path: DimensionRunner.run always routes
        through process_dimension_with_cache."""
        from quodeq.analysis.dimension_runner import DimensionRunner

        config, src = _setup(tmp_path, {"a.py": "x"})

        called = {"hit": False}
        def fake_cache(config, dim_id, idx, ctx, callbacks, cache=None):
            called["hit"] = True
            return _make_dummy_evidence(files_read=1)

        with patch(
            "quodeq.analysis.dimension_runner.process_dimension_with_cache",
            new=fake_cache,
        ):
            DimensionRunner().run(config, "security", 1, _make_ctx(), emit_log=False)

        assert called["hit"] is True


class TestDispatchKeysSidecar:
    def test_sidecar_written_with_miss_keys(self, tmp_path: Path, cache):
        from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        sidecar = (config.work_dir or config.src) / "security_dispatch_keys.json"
        assert sidecar.is_file()
        keys = json.loads(sidecar.read_text())
        expected_keys = {
            "a.py": build_cache_key_for_file(config, "a.py", "security"),
            "b.py": build_cache_key_for_file(config, "b.py", "security"),
        }
        assert keys == expected_keys

    def test_sidecar_skipped_when_all_hits(self, tmp_path: Path, cache):
        """All-hits short-circuit returns before reaching the dispatch path,
        so no sidecar is written. Discard for an all-hits dim has nothing
        to wipe anyway."""
        from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
        config, src = _setup(tmp_path, {"a.py": "x"})
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "v"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        assert dispatcher.calls == []  # confirm we hit the all-hits path
        sidecar = (config.work_dir or config.src) / "security_dispatch_keys.json"
        assert not sidecar.exists()


# ============================================================
# Circuit breaker (Slice 5)
# ============================================================


class TestCircuitBreakerWiring:
    def test_breaker_trips_and_raises(self, tmp_path: Path, cache, monkeypatch):
        """Threshold=2 + dispatcher emits 2 error markers => CircuitBreakerError."""
        from quodeq.analysis.cache._failure_streak import CircuitBreakerError
        from quodeq.shared import cancellation
        cancellation.reset()

        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})
        config = replace(config, options=replace(config.options, failure_streak_threshold=2))

        evidence_dir = config.work_dir or config.src

        def err_dispatcher(config, dim_id, idx, ctx, callbacks):
            jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "_marker": "file_done", "file": "a.py",
                    "status": "error", "reason": "token_limit",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "b.py",
                    "status": "error", "reason": "token_limit",
                }) + "\n")
            # No sleep: the breaker does a final scan on stop (see
            # FailureStreakWatcher._run), so the trip is detected once dispatch
            # returns rather than depending on a poll landing mid-dispatch.
            return _make_dummy_evidence(files_read=2)

        try:
            with patch(
                "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
                new=err_dispatcher,
            ):
                with pytest.raises(CircuitBreakerError) as excinfo:
                    process_dimension_with_cache(
                        config, "security", idx=1, ctx=_make_ctx(),
                        callbacks=_make_callbacks(), cache=cache,
                    )
            assert excinfo.value.reason == "circuit_breaker"
            assert cancellation.is_cancelled()
        finally:
            cancellation.reset()

    def test_breaker_disabled_when_threshold_zero(
        self, tmp_path: Path, cache, monkeypatch,
    ):
        """threshold=0 disables the breaker even with many error markers."""
        from quodeq.shared import cancellation
        cancellation.reset()

        config, src = _setup(tmp_path, {"a.py": "x"})
        config = replace(config, options=replace(config.options, failure_streak_threshold=0))

        evidence_dir = config.work_dir or config.src

        def err_dispatcher(config, dim_id, idx, ctx, callbacks):
            jsonl = evidence_dir / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                for i in range(10):
                    out.write(json.dumps({
                        "_marker": "file_done", "file": f"f{i}.py",
                        "status": "error",
                    }) + "\n")
            return _make_dummy_evidence(files_read=10)

        try:
            with patch(
                "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
                new=err_dispatcher,
            ):
                # Should NOT raise CircuitBreakerError.
                ev = process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
                )
            assert ev is not None
            assert not cancellation.is_cancelled()
        finally:
            cancellation.reset()


# ============================================================
# Carry order: cached findings appear FIRST in the JSONL
# ============================================================
#
# Pre-fix, cached findings were appended AFTER dispatch wrote its fresh
# findings, producing two effects users complained about:
#  1. The merged JSONL ordered fresh-then-cached, so the final report
#     read "new findings, then carries" -- the opposite of how a user
#     thinks about it ("carries are foundation, fresh is on top").
#  2. The dispatcher's internal dedup ran BEFORE we appended cached
#     findings, producing two log lines like "Deduplicated ...: 27"
#     followed by "Deduplicated ...: 55", visibly confusing.
#
# Now: cached findings are pre-written to the JSONL BEFORE dispatch.
# Dispatch's internal dedup sees the merged set in one pass.


class TestCarryOrder:
    def test_cached_findings_appear_before_fresh(self, tmp_path: Path, cache):
        """Pre-populate cache for one file. Dispatch a different file. The
        JSONL should have the cached file's findings BEFORE the dispatched
        file's findings (carries first, then fresh)."""
        from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
        from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file

        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Cache a.py with a recognizable finding.
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation",
                       "w": "carry-a", "p": "P1", "d": "security",
                       "req": "X-1", "severity": "minor",
                       "snippet": "x", "reason": "r"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        # b.py is a miss -- fake dispatcher writes a fresh finding for it.
        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks):
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "file": "b.py", "line": 1, "t": "violation",
                    "w": "fresh-b", "p": "P2", "d": "security",
                    "req": "X-2", "severity": "minor",
                    "snippet": "y", "reason": "r",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "b.py", "status": "ok",
                }) + "\n")
            return _make_dummy_evidence(files_read=1)

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatch,
        ):
            process_dimension_with_cache(
                config, "security", 1, _make_ctx(),
                _make_callbacks(), cache=cache,
            )

        jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
        lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
        # Filter to actual finding lines (not markers).
        findings = [ln for ln in lines if "_marker" not in ln]
        # Carry comes first; fresh comes second.
        assert findings[0]["w"] == "carry-a", (
            f"expected carry-a first, got {[f.get('w') for f in findings]}"
        )
        assert any(f.get("w") == "fresh-b" for f in findings), (
            "fresh dispatch finding missing from JSONL"
        )
        # Specifically: the carry comes before the fresh in JSONL order.
        carry_idx = next(i for i, f in enumerate(findings) if f.get("w") == "carry-a")
        fresh_idx = next(i for i, f in enumerate(findings) if f.get("w") == "fresh-b")
        assert carry_idx < fresh_idx, (
            f"carry (index {carry_idx}) should appear before fresh (index {fresh_idx})"
        )


class TestWatcherJoinHasNoTimeoutCeiling:
    """Regression for the c88be50e "16% loss" bug.

    The watcher's final persist tick can take longer than 5s when the
    JSONL has a few hundred file_done="ok" markers (each tick re-scans
    the full file and writes per-file cache entries). A 5s join ceiling
    silently abandoned the final tick mid-flight, so every `ok` marker
    that hadn't been persisted by the previous tick was lost.

    The user reported a flexibility run where 790 file_done="ok" markers
    landed in the JSONL but only 662 cache entries persisted (~16% loss).

    Pin via source inspection so a future refactor can't re-introduce the
    timeout. The watcher.join() call MUST stay un-timeout-bounded; the
    breaker is a separate thread and keeps its own timeout.
    """

    def test_final_cache_flush_has_no_join_timeout_ceiling(self):
        import inspect

        from quodeq.analysis.cache import dimension_runner

        src = inspect.getsource(dimension_runner.process_dimension_with_cache)
        assert "watcher.join(timeout=5.0)" not in src, (
            "watcher.join must not have a timeout ceiling — the 5s cap "
            "was the c88be50e regression that dropped the final persist tick"
        )
        assert "watcher.join()" in src, (
            "watcher.join() (no timeout) must still run in the finally "
            "block so the final persist tick completes"
        )

    def test_breaker_join_keeps_its_timeout(self):
        """The breaker is a separate thread with its own lifecycle —
        its 5s join cap is unrelated to the cache-loss bug and should
        remain intact."""
        import inspect

        from quodeq.analysis.cache import dimension_runner

        src = inspect.getsource(dimension_runner.process_dimension_with_cache)
        assert "breaker.stop_and_join(timeout=5.0)" in src, (
            "breaker.stop_and_join's 5s timeout is independent of the "
            "watcher fix and must stay in place"
        )


class TestCachedFindingsReachEventLog:
    """Pin that cache-replayed findings land in ``events.jsonl`` as
    ``JUDGMENT_CREATED`` events, not only in the per-dim JSONL.

    Without this, an incremental run's SQL projection (which reads
    ``events.jsonl``) sees only the freshly-dispatched findings — the
    dashboard grade tables disagree with the CLI's JSON output because
    they're scoring different sets of findings. The user reported this as
    "flexibility shows 7.7 in the CLI but 9.0 in the UI" on a real
    incremental run; the gap was exactly the cache-restored findings.
    """

    def _read_events(self, events_log: Path) -> list[dict]:
        if not events_log.exists():
            return []
        out = []
        for line in events_log.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out

    def test_all_hits_run_emits_judgment_events_for_cache_replay(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Pre-populate cache for both files so the run short-circuits dispatch.
        for f in ["a.py", "b.py"]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1,
                findings=[{
                    "file": f, "line": 7, "t": "violation",
                    "w": f"cached-{f}", "p": "Confidentiality", "d": "security",
                    "req": f"S-CON-{f}", "severity": "minor",
                    "snippet": "s", "reason": "r",
                }],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        dispatcher = FakeDispatcher(src)
        # events.jsonl lives at <evidence_dir>/.. which is <work_dir>/..
        # The runner derives this from the per-dim JSONL path internally.
        events_log = (config.work_dir or config.src).parent / "events.jsonl"

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        assert dispatcher.calls == [], "all-hits path must not dispatch"

        events = self._read_events(events_log)
        # Every cached finding must produce a JUDGMENT_CREATED event so the
        # SQL projection sees it. Without the fix this list would be empty.
        judgments = [e for e in events if e.get("event_type") == "JUDGMENT_CREATED"]
        files_in_events = {e["payload"]["file"] for e in judgments}
        assert files_in_events == {"a.py", "b.py"}, (
            f"events.jsonl must contain a JUDGMENT_CREATED per cached finding; "
            f"got {files_in_events}"
        )

    def test_partial_run_emits_judgment_events_for_carried_findings(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Mixed run: one cached hit (a.py) + one dispatched miss (b.py).

        The cached carry was the silently-dropped path — pin that it shows
        up in events.jsonl alongside the dispatcher's own emit.
        """
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[{
                "file": "a.py", "line": 1, "t": "violation",
                "w": "carry-a", "p": "Confidentiality", "d": "security",
                "req": "S-CON-A", "severity": "minor",
                "snippet": "x", "reason": "r",
            }],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        events_log = (config.work_dir or config.src).parent / "events.jsonl"

        def fake_dispatch(cfg, dim_id, idx, ctx, callbacks):
            # The dispatcher in production routes through FindingsRouter,
            # which emits events. This fake only writes JSONL — we're
            # specifically testing the cache-replay side.
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                out.write(json.dumps({
                    "file": "b.py", "line": 1, "t": "violation",
                    "w": "fresh-b", "p": "Confidentiality", "d": "security",
                    "req": "S-CON-B", "severity": "minor",
                    "snippet": "y", "reason": "r",
                }) + "\n")
            return _make_dummy_evidence(files_read=1)

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=fake_dispatch,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        events = self._read_events(events_log)
        carry_files = {
            e["payload"]["file"] for e in events
            if e.get("event_type") == "JUDGMENT_CREATED"
        }
        assert "a.py" in carry_files, (
            f"cached carry for a.py must emit a JUDGMENT_CREATED event; "
            f"got {carry_files}"
        )


# ============================================================
# files_read reflects analyzed count, not input list size
# ============================================================
#
# Pre-fix, every callsite of parse_evidence_from_jsonl in
# process_dimension_with_cache passed ``files_read=len(files)``. That
# made coverage % (computed downstream as files_read / source_file_count)
# always 100% even when the run only finished a fraction of its files —
# e.g. a deadline-truncated flexibility run that analyzed 850/3037 files
# scored "6.6/Adequate" on a dashboard that couldn't tell it was partial.
#
# The honest signal: files_read = cache hits + dispatch files whose
# most recent file_done marker is "ok". Files with file_done="error"
# (worker crashed, token-out) or no marker at all are NOT counted —
# their analysis was incomplete, the cache has no entry for them, and
# the next run will re-dispatch.


class TestEvidenceFileCreatedBeforeBreaker:
    """A fresh dimension (all misses, no cached findings) must not spam
    'Could not read failure-streak JSONL' warnings at startup.

    Repro: in the window before any finding lands, the per-dim evidence
    JSONL doesn't exist yet. The FailureStreakWatcher polls it anyway and
    every scan of the missing file logs a WARNING (the user saw this once
    per heartbeat on a 1324-file dimension). The runner now touches the
    evidence file before starting the breaker, so the watcher always reads
    an existing (possibly empty) file and stays silent.
    """

    def test_no_startup_warning_when_dispatch_writes_nothing(
        self, tmp_path: Path, cache: LocalFileBackend, monkeypatch,
    ):
        from quodeq.shared import cancellation
        cancellation.reset()
        # QUODEQ_FAILURE_STREAK overrides the options field, so clear it to
        # keep threshold=5 below authoritative — otherwise a stray `=0` in
        # the environment would disable the breaker and false-green this.
        monkeypatch.delenv("QUODEQ_FAILURE_STREAK", raising=False)

        config, src = _setup(tmp_path, {"a.py": "x"})
        # Breaker must be enabled (threshold > 0) so the watcher actually
        # scans the JSONL — a disabled breaker runs a no-op thread.
        config = replace(
            config, options=replace(config.options, failure_streak_threshold=5),
        )

        # Dispatcher that writes NOTHING to the JSONL and returns None,
        # mirroring the fresh-dimension window before any finding is emitted.
        def silent_dispatcher(cfg, dim_id, idx, ctx, callbacks):
            return None

        # Capture WARNING+ only, so the assertion isn't coupled to the exact
        # warning string — any startup warning from the breaker fails the test.
        handler = _ListHandler()
        handler.setLevel(logging.WARNING)
        breaker_logger = logging.getLogger(
            "quodeq.analysis.cache._failure_streak"
        )
        breaker_logger.addHandler(handler)
        try:
            with patch(
                "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
                new=silent_dispatcher,
            ):
                process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
                )
        finally:
            breaker_logger.removeHandler(handler)
            cancellation.reset()

        jsonl = (config.work_dir or config.src) / "security_evidence.jsonl"
        assert jsonl.exists(), (
            "evidence JSONL must be created before the breaker starts so the "
            "watcher never reads a missing file"
        )
        # Happy path (empty file, no error markers): the breaker emits no
        # WARNING+ records at all — not the missing-file warning, nothing.
        assert handler.messages == [], (
            "failure-streak watcher logged unexpected warning(s) at startup; "
            f"messages={handler.messages}"
        )


class TestCacheReplayAppliesProvenanceGate:
    """Issue #657: findings replayed from a pre-#639 cache entry must pass
    through the deterministic provenance gate too.

    The live finding path gates in ``FindingEnricher.enrich()``, but cache
    replay (``_write_findings``) writes cached findings straight to the
    per-dim JSONL and the event log, bypassing ``enrich()``. A stale,
    un-gated ``critical`` R-FT-2 / S-AUT-3 finding produced by an older
    quodeq version would otherwise replay at ``critical`` and inflate the
    grade. Re-gating on the replay write path keeps cached and
    freshly-dispatched findings consistent.
    """

    @staticmethod
    def _cached_critical(file: str, reason: str) -> dict:
        return {
            "file": file, "line": 1, "t": "violation",
            "w": "Unguarded index access", "p": "Fault Tolerance",
            "d": "security", "req": "R-FT-2", "severity": "critical",
            "snippet": "arr[idx]", "reason": reason,
        }

    @staticmethod
    def _findings_in(jsonl: Path) -> list[dict]:
        return [
            json.loads(ln) for ln in jsonl.read_text().splitlines()
            if ln.strip() and "_marker" not in ln
        ]

    def _replay_all_hits(
        self, tmp_path: Path, cache: LocalFileBackend, reason: str,
    ) -> tuple[RunConfig, FakeDispatcher]:
        config, src = _setup(tmp_path, {"a.py": "x"})
        key = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key, CacheEntry(
            key=key, schema_version=1,
            findings=[self._cached_critical("a.py", reason)],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))
        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )
        assert dispatcher.calls == [], "all-hits path must not dispatch"
        return config, dispatcher

    def test_cached_critical_without_external_source_is_downgraded(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # A pre-#639 critical R-FT-2 whose reason names no external ingress
        # source -- "argument" is deliberately NOT a trust-boundary term.
        config, _ = self._replay_all_hits(
            tmp_path, cache,
            "Index derived from a function argument with no bounds check.",
        )

        jsonl = (config.work_dir or config.src) / "security_evidence.jsonl"
        findings = self._findings_in(jsonl)
        assert len(findings) == 1
        assert findings[0]["severity"] == "major", (
            "cache-replayed critical R-FT-2 without an external source must "
            "be downgraded to major by the provenance gate"
        )
        assert findings[0].get("provenance_downgrade") is True

        # The gated severity must also reach the event log -- that's the
        # path the SQL projection / grade reads, so a stale critical here
        # would still inflate the score even after the JSONL was fixed.
        events_log = (config.work_dir or config.src).parent / "events.jsonl"
        events = [
            json.loads(ln) for ln in events_log.read_text().splitlines()
            if ln.strip()
        ] if events_log.exists() else []
        judgments = [e for e in events if e.get("event_type") == "JUDGMENT_CREATED"]
        assert judgments, "cache replay must emit a JUDGMENT_CREATED event"
        assert judgments[0]["payload"]["severity"] == "major", (
            "the gated severity must reach events.jsonl, not the stale critical"
        )

    def test_cached_critical_naming_external_source_is_preserved(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        # Same finding, but the reason names a reachable external source --
        # the gate must leave it critical.
        config, _ = self._replay_all_hits(
            tmp_path, cache,
            "Index taken straight from the HTTP request body, unvalidated.",
        )

        jsonl = (config.work_dir or config.src) / "security_evidence.jsonl"
        findings = self._findings_in(jsonl)
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical", (
            "a cache-replayed critical naming an external source must NOT be "
            "downgraded"
        )
        assert "provenance_downgrade" not in findings[0]


class TestFilesReadReflectsAnalyzedCount:
    """files_read on the returned Evidence must equal the number of source
    files reproducible from cache at run end — NOT len(input_files)."""

    def test_files_read_equals_total_when_all_cache_hits(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """All-hits short-circuit: every input file is a cache hit.
        files_read must equal len(files)."""
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})

        # Pre-populate cache for every input file.
        for f in ["a.py", "b.py", "c.py"]:
            key = build_cache_key_for_file(config, f, "security")
            cache.put(key, CacheEntry(
                key=key, schema_version=1,
                findings=[{"file": f, "line": 1, "t": "violation", "w": f"v-{f}"}],
                files_read=1, file_path=f, dimension="security",
                model_id="test-model",
            ))

        dispatcher = FakeDispatcher(src)
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        assert dispatcher.calls == [], "all-hits path must not dispatch"
        assert ev is not None
        assert ev.files_read == 3, (
            f"all-hits run must report files_read=3, got {ev.files_read}"
        )

    def test_files_read_equals_hits_plus_ok_dispatches(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """3 source files: 1 cache hit, 1 dispatches with file_done='ok',
        1 dispatches with file_done='error'. Expect files_read=2 (hit + ok).
        """
        config, src = _setup(
            tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"},
        )

        # Pre-seed cache for a.py only — b.py and c.py are misses.
        key_a = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key_a, CacheEntry(
            key=key_a, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "cached-a"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        def mixed_dispatcher(cfg, dim_id, idx, ctx, callbacks):
            # Misses are restricted by the file filter to {b.py, c.py}.
            jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
            jsonl.parent.mkdir(parents=True, exist_ok=True)
            with jsonl.open("a") as out:
                # b.py completes with ok marker — counts toward files_read.
                out.write(json.dumps({
                    "file": "b.py", "line": 1, "t": "violation", "w": "fresh-b",
                }) + "\n")
                out.write(json.dumps({
                    "_marker": "file_done", "file": "b.py", "status": "ok",
                }) + "\n")
                # c.py errors out — must NOT count toward files_read.
                out.write(json.dumps({
                    "_marker": "file_done", "file": "c.py",
                    "status": "error", "reason": "token_limit",
                }) + "\n")
            return _make_dummy_evidence(files_read=2)

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=mixed_dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        assert ev is not None
        # a.py = cache hit (1). b.py = ok dispatch (1). c.py = errored (0).
        assert ev.files_read == 2, (
            f"expected files_read=2 (hit + ok), got {ev.files_read}; "
            f"source_file_count={ev.source_file_count}"
        )
        assert ev.source_file_count == 3, (
            f"source_file_count must equal len(input files) = 3, "
            f"got {ev.source_file_count}"
        )

    def test_files_read_when_dispatch_returns_none_with_carries(
        self, tmp_path: Path, cache: LocalFileBackend,
    ):
        """Dispatch returns None but cached findings exist — the
        ``classify.cached_findings and jsonl.exists()`` branch must also
        use the computed files_read (= just the cache hits, since no
        dispatched files have ok markers)."""
        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

        # Pre-populate a.py only.
        key_a = build_cache_key_for_file(config, "a.py", "security")
        cache.put(key_a, CacheEntry(
            key=key_a, schema_version=1,
            findings=[{"file": "a.py", "line": 1, "t": "violation", "w": "cached-a"}],
            files_read=1, file_path="a.py", dimension="security",
            model_id="test-model",
        ))

        # Dispatch returns None (no fresh findings, no markers written).
        def failing_dispatcher(*args, **kwargs):
            return None

        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=failing_dispatcher,
        ):
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
            )

        assert ev is not None, (
            "dispatch returned None but cached findings should still produce "
            "Evidence via the pre-written JSONL"
        )
        # Only a.py is reproducible — b.py's dispatch produced no ok marker.
        assert ev.files_read == 1, (
            f"expected files_read=1 (just the cache hit), got {ev.files_read}"
        )


def _finding_line(file: str) -> str:
    """A realistic violation finding (the producer's compact schema) that the
    evidence parser groups under principle ``Adaptability``."""
    return json.dumps({
        "schema_version": 1, "req": "F-ADP-1", "t": "violation",
        "file": file, "line": 1, "severity": "minor",
        "w": "hardcoded value", "snippet": "x = 1",
        "reason": "hardcoded environment-specific value",
        "p": "Adaptability", "d": "flexibility",
    })


class _SalvageDispatcher:
    """Writes one real finding + N consecutive error markers to trip the breaker.

    Models a dimension whose model calls start failing after some real work
    has already been persisted to the JSONL.
    """

    def __init__(self, n_errors: int) -> None:
        self.n_errors = n_errors

    def __call__(self, config, dim_id, idx, ctx, callbacks):
        jsonl = (config.work_dir or config.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            out.write(_finding_line("a.py") + "\n")
            out.write(json.dumps(
                {"_marker": "file_done", "file": "a.py", "status": "ok"}) + "\n")
            for i in range(self.n_errors):
                out.write(json.dumps({
                    "_marker": "file_done", "file": f"e{i}.py",
                    "status": "error", "reason": "model call failed",
                }) + "\n")
        return None


class _AllErrorsDispatcher:
    """Writes only error markers — nothing to salvage."""

    def __init__(self, n_errors: int) -> None:
        self.n_errors = n_errors

    def __call__(self, config, dim_id, idx, ctx, callbacks):
        jsonl = (config.work_dir or config.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            for i in range(self.n_errors):
                out.write(json.dumps({
                    "_marker": "file_done", "file": f"e{i}.py",
                    "status": "error", "reason": "model call failed",
                }) + "\n")
        return None


class TestBreakerSalvage:
    @pytest.fixture(autouse=True)
    def _reset_cancel(self):
        from quodeq.shared import cancellation
        cancellation.reset()
        yield
        cancellation.reset()

    def test_breaker_trip_salvages_partial_evidence(self, tmp_path, cache):
        config, _src = _setup(tmp_path, {"a.py": "x"})
        config = replace(
            config, options=replace(config.options, failure_streak_threshold=3))
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=_SalvageDispatcher(n_errors=3),
        ):
            ev = process_dimension_with_cache(
                config, "flexibility", 1, _make_ctx(), _make_callbacks(), cache=cache)
        assert ev is not None, "breaker trip should salvage collected findings, not discard"
        assert ev.exit_reason == "failure_streak"
        assert ev.principles, "salvaged Evidence should carry the collected findings"

    def test_breaker_trip_with_no_findings_raises(self, tmp_path, cache):
        config, _src = _setup(tmp_path, {"a.py": "x"})
        config = replace(
            config, options=replace(config.options, failure_streak_threshold=3))
        with patch(
            "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
            new=_AllErrorsDispatcher(n_errors=3),
        ):
            with pytest.raises(CircuitBreakerError):
                process_dimension_with_cache(
                    config, "flexibility", 1, _make_ctx(), _make_callbacks(), cache=cache)
