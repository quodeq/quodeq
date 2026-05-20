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
            # Give the watcher's poll loop time to read both errors and trip.
            import time as _time
            _time.sleep(1.0)
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
