"""process_dimension_with_cache — circuit breaker (Slice 5).

Split from test_dimension_runner.py: breaker trip/disable wiring, the
startup-warning regression for a fresh dimension, the breaker's own
join-timeout pin, and partial-evidence salvage on trip. Shared
scaffolding lives in tests/analysis/cache/conftest.py.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from quodeq.analysis.cache._failure_streak import CircuitBreakerError
from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache
from tests.analysis.cache.conftest import (
    _ListHandler,
    _make_callbacks,
    _make_ctx,
    _make_dummy_evidence,
    _setup,
)


class TestCircuitBreakerWiring:
    def test_breaker_trips_and_raises(self, tmp_path: Path, cache, monkeypatch):
        """Threshold=2 + dispatcher emits 2 error markers => CircuitBreakerError."""
        from quodeq.shared import cancellation
        cancellation.reset()

        config, src = _setup(tmp_path, {"a.py": "x", "b.py": "y", "c.py": "z"})
        config = replace(config, options=replace(config.options, failure_streak_threshold=2))

        evidence_dir = config.work_dir or config.src

        def err_dispatcher(config, dim_id, idx, ctx, callbacks, **_):
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
            with pytest.raises(CircuitBreakerError) as excinfo:
                process_dimension_with_cache(
                    config, "security", idx=1, ctx=_make_ctx(),
                    callbacks=_make_callbacks(), cache=cache,
                    dispatcher=err_dispatcher,
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

        def err_dispatcher(config, dim_id, idx, ctx, callbacks, **_):
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
            # Should NOT raise CircuitBreakerError.
            ev = process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
                dispatcher=err_dispatcher,
            )
            assert ev is not None
            assert not cancellation.is_cancelled()
        finally:
            cancellation.reset()


def test_breaker_join_keeps_its_timeout():
    """The breaker is a separate thread with its own lifecycle —
    its 5s join cap is unrelated to the c88be50e cache-loss bug and
    should remain intact. (The watcher.join() no-timeout behavior is
    pinned behaviorally by TestSlowFinalPersistIsNotAbandoned in
    test_dimension_runner_persistence.py.)"""
    import inspect

    from quodeq.analysis.cache import dimension_runner

    src = inspect.getsource(dimension_runner.process_dimension_with_cache)
    assert "breaker.stop_and_join(timeout=5.0)" in src, (
        "breaker.stop_and_join's 5s timeout is independent of the "
        "watcher fix and must stay in place"
    )


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
        self, tmp_path: Path, cache, monkeypatch,
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
        def silent_dispatcher(cfg, dim_id, idx, ctx, callbacks, **_):
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
            process_dimension_with_cache(
                config, "security", idx=1, ctx=_make_ctx(),
                callbacks=_make_callbacks(), cache=cache,
                dispatcher=silent_dispatcher,
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

    def __call__(self, config, dim_id, idx, ctx, callbacks, **_):
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

    def __call__(self, config, dim_id, idx, ctx, callbacks, **_):
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
        ev = process_dimension_with_cache(
            config, "flexibility", 1, _make_ctx(), _make_callbacks(), cache=cache, dispatcher=_SalvageDispatcher(n_errors=3))
        assert ev is not None, "breaker trip should salvage collected findings, not discard"
        assert ev.exit_reason == "failure_streak"
        assert ev.principles, "salvaged Evidence should carry the collected findings"

    def test_breaker_trip_with_no_findings_raises(self, tmp_path, cache):
        config, _src = _setup(tmp_path, {"a.py": "x"})
        config = replace(
            config, options=replace(config.options, failure_streak_threshold=3))
        with pytest.raises(CircuitBreakerError):
            process_dimension_with_cache(
                config, "flexibility", 1, _make_ctx(), _make_callbacks(), cache=cache, dispatcher=_AllErrorsDispatcher(n_errors=3))
