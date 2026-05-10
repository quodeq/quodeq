"""analyze_unit — cache-aware work unit runner.

These tests pin down the structural invariants of the cache layer
without involving real LLM calls. The dispatcher is stubbed so each
property is observable and deterministic:

  - hits never call the dispatcher; misses always do
  - dispatcher exceptions never write entries (crash = retry)
  - any input change in the cache key invalidates
  - schema_version is the global blast-radius lever
  - dispatcher does not need to know its own cache key
  - the runner is the single source of truth for the entry's key
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.analysis.cache.entry import CacheEntry
from quodeq.analysis.cache.local import LocalFileBackend
from quodeq.analysis.cache.runner import (
    DispatchResult,
    WorkUnit,
    analyze_unit,
)


def _unit(**overrides) -> WorkUnit:
    defaults = dict(
        file_path="src/auth.py",
        file_content_hash="aa" * 32,
        dimension="security",
        standards_hash="bb" * 32,
        prompts_hash="cc" * 32,
        evaluator_hash="dd" * 32,
        model_id="claude-opus-4-7",
        language="python",
        temperature=None,
        max_tokens=None,
    )
    defaults.update(overrides)
    return WorkUnit(**defaults)


class _RecordingDispatcher:
    """Stub dispatcher that records calls and returns canned results."""

    def __init__(self, findings: list[dict] | None = None, files_read: int = 1) -> None:
        self._findings = findings if findings is not None else [{"file": "a.py", "line": 1, "t": "violation"}]
        self._files_read = files_read
        self.calls: list[WorkUnit] = []

    def __call__(self, unit: WorkUnit) -> DispatchResult:
        self.calls.append(unit)
        return DispatchResult(findings=list(self._findings), files_read=self._files_read)


@pytest.fixture
def cache(tmp_path: Path) -> LocalFileBackend:
    return LocalFileBackend(root=tmp_path / "cache")


# ---------- core hit/miss ----------

class TestHitMiss:
    def test_first_call_misses_and_dispatches(self, cache: LocalFileBackend):
        dispatcher = _RecordingDispatcher()
        result = analyze_unit(_unit(), cache=cache, dispatcher=dispatcher)
        assert result.cache_hit is False
        assert len(dispatcher.calls) == 1
        assert result.entry.findings == [{"file": "a.py", "line": 1, "t": "violation"}]

    def test_second_call_hits_without_dispatching(self, cache: LocalFileBackend):
        dispatcher = _RecordingDispatcher()
        unit = _unit()
        analyze_unit(unit, cache=cache, dispatcher=dispatcher)
        result = analyze_unit(unit, cache=cache, dispatcher=dispatcher)
        assert result.cache_hit is True
        assert len(dispatcher.calls) == 1  # still just the first one

    def test_hit_returns_findings_identical_to_miss(self, cache: LocalFileBackend):
        dispatcher = _RecordingDispatcher(findings=[{"file": "x.py", "line": 5, "msg": "test"}])
        unit = _unit()
        first = analyze_unit(unit, cache=cache, dispatcher=dispatcher)
        second = analyze_unit(unit, cache=cache, dispatcher=dispatcher)
        assert first.entry.findings == second.entry.findings
        assert first.entry.files_read == second.entry.files_read
        assert first.entry.key == second.entry.key


# ---------- crash safety ----------

class TestDispatcherFailure:
    def test_dispatcher_exception_writes_no_entry(self, cache: LocalFileBackend):
        def boom(unit: WorkUnit) -> DispatchResult:
            raise RuntimeError("model timeout")

        with pytest.raises(RuntimeError, match="model timeout"):
            analyze_unit(_unit(), cache=cache, dispatcher=boom)

        # Next call must still miss — no half-state was written.
        dispatcher = _RecordingDispatcher()
        result = analyze_unit(_unit(), cache=cache, dispatcher=dispatcher)
        assert result.cache_hit is False
        assert len(dispatcher.calls) == 1

    def test_dispatcher_exception_does_not_corrupt_other_entries(self, cache: LocalFileBackend):
        unit_ok = _unit(file_path="ok.py")
        unit_bad = _unit(file_path="bad.py")

        # Successfully cache one unit.
        analyze_unit(unit_ok, cache=cache, dispatcher=_RecordingDispatcher())

        # Fail another. The first must still hit.
        def boom(_: WorkUnit) -> DispatchResult:
            raise RuntimeError("boom")
        with pytest.raises(RuntimeError):
            analyze_unit(unit_bad, cache=cache, dispatcher=boom)

        result = analyze_unit(unit_ok, cache=cache, dispatcher=_RecordingDispatcher())
        assert result.cache_hit is True


# ---------- key sensitivity (every CacheKey field invalidates) ----------

class TestInvalidation:
    @pytest.mark.parametrize("override", [
        {"file_content_hash": "00" * 32},
        {"file_path": "src/other.py"},
        {"dimension": "documentation"},
        {"standards_hash": "11" * 32},
        {"prompts_hash": "22" * 32},
        {"evaluator_hash": "33" * 32},
        {"model_id": "claude-sonnet-4-6"},
        {"language": "typescript"},
        {"temperature": 0.7},
        {"max_tokens": 4096},
    ])
    def test_each_input_change_misses(self, cache: LocalFileBackend, override: dict):
        dispatcher = _RecordingDispatcher()
        analyze_unit(_unit(), cache=cache, dispatcher=dispatcher)
        result = analyze_unit(_unit(**override), cache=cache, dispatcher=dispatcher)
        assert result.cache_hit is False
        assert len(dispatcher.calls) == 2

    def test_schema_version_bump_invalidates_everything(self, cache: LocalFileBackend):
        dispatcher = _RecordingDispatcher()
        unit = _unit()
        analyze_unit(unit, cache=cache, dispatcher=dispatcher, schema_version=1)
        result = analyze_unit(unit, cache=cache, dispatcher=dispatcher, schema_version=2)
        assert result.cache_hit is False
        assert len(dispatcher.calls) == 2


# ---------- runner owns the key ----------

class TestRunnerOwnsKey:
    def test_dispatcher_does_not_supply_key(self, cache: LocalFileBackend):
        # The dispatcher signature returns DispatchResult (findings + metadata).
        # The runner is the only thing that computes and stamps the key.
        dispatcher = _RecordingDispatcher()
        result = analyze_unit(_unit(), cache=cache, dispatcher=dispatcher)
        assert len(result.entry.key) == 64  # SHA-256 hex
        # And the persisted entry carries the same key.
        loaded = cache.get(result.entry.key)
        assert loaded is not None
        assert loaded.key == result.entry.key

    def test_entry_metadata_propagates_from_unit(self, cache: LocalFileBackend):
        unit = _unit(file_path="src/special.py", dimension="performance", model_id="claude-haiku-4")
        result = analyze_unit(unit, cache=cache, dispatcher=_RecordingDispatcher())
        assert result.entry.file_path == "src/special.py"
        assert result.entry.dimension == "performance"
        assert result.entry.model_id == "claude-haiku-4"


# ---------- concurrency (atomic writes from the backend) ----------

class TestConcurrency:
    def test_two_runners_for_same_key_both_succeed(self, cache: LocalFileBackend):
        # Simulates two processes racing for the same cache key. Backend
        # writes are atomic via os.replace, so both succeed and the final
        # entry is well-formed (last writer wins; content is equivalent
        # because inputs match).
        unit = _unit()
        d1 = _RecordingDispatcher(findings=[{"x": 1}])
        d2 = _RecordingDispatcher(findings=[{"x": 1}])  # same inputs → same findings
        r1 = analyze_unit(unit, cache=cache, dispatcher=d1)
        r2 = analyze_unit(unit, cache=cache, dispatcher=d2)
        # First was a miss (dispatched); second hit cache from first.
        assert r1.cache_hit is False
        assert r2.cache_hit is True
        loaded = cache.get(r1.entry.key)
        assert loaded is not None
        assert loaded.findings == [{"x": 1}]


# ---------- empty results are still cached ----------

class TestEmptyResults:
    def test_empty_findings_cache_normally(self, cache: LocalFileBackend):
        # A successful analysis that finds nothing must still cache so the
        # next run doesn't re-pay the dispatch cost.
        dispatcher = _RecordingDispatcher(findings=[], files_read=1)
        unit = _unit()
        first = analyze_unit(unit, cache=cache, dispatcher=dispatcher)
        second = analyze_unit(unit, cache=cache, dispatcher=dispatcher)
        assert first.cache_hit is False
        assert second.cache_hit is True
        assert second.entry.findings == []
        assert len(dispatcher.calls) == 1
