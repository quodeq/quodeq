"""Tests for the safety properties of the dimension loops.

These pin down the guarantee that motivated the diagnostic + widened
exception trap: a broken pipe (or any unexpected exception) raised by
the per-dim runner *or* by the result/scoring callback must not drop
subsequent iterations on the floor. The bug we observed in production:
usability finished its queue, the dashboard's scoring callback raised
``BrokenPipeError`` while writing to a closed parent pipe, the
exception propagated out of the loop, the lifecycle's
``BrokenPipeError`` handler quietly converted state to ``done`` —
flexibility never ran, usability's eval file was never written, and
nothing in the run.log told us where the gap was.

The fix this file pins down: catch broken-pipe / generic exceptions
from both the dim runner *and* the callback inside the loop, log a
diagnostic, keep the result, continue iterating.
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from quodeq.analysis._loops import run_incremental_loop, run_per_dimension_loop
from quodeq.analysis._types import _AnalysisContext


def _ctx(total: int) -> _AnalysisContext:
    """Minimal _AnalysisContext — only `total` is read by the loops."""
    return _AnalysisContext(
        dimensions_data=None,
        date_str="",
        template="",
        subagent_template="",
        total=total,
    )


def _config() -> MagicMock:
    """Minimal RunConfig stub for the few fields the loops dereference.

    ``skip_scoring=True`` makes ``check_zero_findings`` short-circuit so the
    safety tests can use a stub Evidence without wiring real principle data.
    """
    cfg = MagicMock()
    cfg.source_file_count = 100
    cfg.options.incremental_file_filter = None
    cfg.options.skip_scoring = True
    return cfg


@dataclass
class _FakeEvidence:
    files_read: int = 5
    # check_zero_findings (called after the loop) iterates principles —
    # an empty dict satisfies it without any findings logic.
    principles: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.principles is None:
            object.__setattr__(self, "principles", {})


# ---------------------------------------------------------------------------
# run_per_dimension_loop
# ---------------------------------------------------------------------------

class TestPerDimLoopSafety:
    def test_callback_broken_pipe_does_not_drop_subsequent_dims(self):
        """The bug we observed: scoring callback writes to closed pipe,
        BrokenPipeError propagates, loop terminates early."""
        cfg = _config()
        seen_dims: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen_dims.append(dim)
            return _FakeEvidence()

        callback_calls: list[str] = []
        def on_done(dim, _ev):
            callback_calls.append(dim)
            if dim == "usability":  # exact bug: usability's callback dies
                raise BrokenPipeError("parent pipe closed")

        result = run_per_dimension_loop(
            cfg, ["security", "usability", "flexibility"], _ctx(3),
            process_fn=process_fn, on_dimension_done=on_done,
        )
        # All three dims iterated despite usability's callback raising.
        assert seen_dims == ["security", "usability", "flexibility"]
        # Result still includes usability (we kept the evidence).
        assert set(result) == {"security", "usability", "flexibility"}
        # Callback fired for all three (loop didn't bail early).
        assert callback_calls == ["security", "usability", "flexibility"]

    def test_callback_generic_exception_does_not_drop_subsequent_dims(self):
        cfg = _config()
        seen: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen.append(dim)
            return _FakeEvidence()

        def on_done(dim, _ev):
            if dim == "reliability":
                raise AttributeError("boom")  # arbitrary class loop didn't catch before

        result = run_per_dimension_loop(
            cfg, ["security", "reliability", "performance"], _ctx(3),
            process_fn=process_fn, on_dimension_done=on_done,
        )
        assert seen == ["security", "reliability", "performance"]
        assert set(result) == {"security", "reliability", "performance"}

    def test_unexpected_exception_in_runner_logs_and_continues(self):
        cfg = _config()
        seen: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen.append(dim)
            if dim == "security":
                raise AttributeError("not in the catch list")  # not OSError/Value/etc.
            return _FakeEvidence()

        result = run_per_dimension_loop(
            cfg, ["security", "reliability"], _ctx(2),
            process_fn=process_fn,
        )
        # Both iterations attempted; security skipped, reliability succeeds.
        assert seen == ["security", "reliability"]
        assert "security" not in result
        assert "reliability" in result

    def test_diagnostic_log_lines_are_emitted(self):
        cfg = _config()
        with patch("quodeq.analysis._loops.log_info") as mock_log:
            run_per_dimension_loop(
                cfg, ["a", "b"], _ctx(2),
                process_fn=lambda *a, **k: _FakeEvidence(),
            )
        messages = [c.args[0] for c in mock_log.call_args_list]
        # Loop start banner
        assert any("per-dimension: 2 dim(s) to process: a, b" in m for m in messages)
        # Per-iteration entry + completion
        assert any("entering iteration 1/2 for a" in m for m in messages)
        assert any("completed iteration 1/2 for a" in m for m in messages)
        assert any("entering iteration 2/2 for b" in m for m in messages)
        assert any("completed iteration 2/2 for b" in m for m in messages)
        # Final summary
        assert any("per-dimension finished: processed 2 of 2 dim(s)" in m for m in messages)


# ---------------------------------------------------------------------------
# run_incremental_loop
# ---------------------------------------------------------------------------

class TestIncrementalLoopSafety:
    def test_callback_broken_pipe_does_not_drop_subsequent_dims(self):
        # Same bug class as per-dim, but on the incremental path which is
        # what the production run was using when usability + flexibility
        # got dropped together.
        cfg = _config()
        seen: list[str] = []
        callback_calls: list[str] = []

        def fake_runner(_c, dim, _i, _ctx):
            seen.append(dim)
            return _FakeEvidence()

        def log_result(_ev, dim, _i, _t):
            if dim == "usability":
                raise BrokenPipeError("dashboard pipe closed")

        def on_done(dim, _ev):
            callback_calls.append(dim)

        with patch("quodeq.analysis._loops.run_dimension_incremental", side_effect=fake_runner):
            result = run_incremental_loop(
                cfg, ["security", "usability", "flexibility"], _ctx(3),
                process_fn=MagicMock(),  # only used as fallback if the inner runner raises
                log_result_fn=log_result,
                on_dimension_done=on_done,
            )

        # All three iterated — flexibility ran despite usability's callback dying.
        assert seen == ["security", "usability", "flexibility"]
        # All three results captured (we keep the evidence even when callback fails).
        assert set(result) == {"security", "usability", "flexibility"}
        # on_done fired for security and flexibility; usability's loop body
        # bailed out of the try at log_result_fn so on_done didn't fire for it.
        assert "usability" not in callback_calls

    def test_unexpected_exception_in_runner_logs_and_continues(self):
        cfg = _config()
        seen: list[str] = []

        def fake_runner(_c, dim, _i, _ctx):
            seen.append(dim)
            if dim == "reliability":
                raise AttributeError("not in catch list")
            return _FakeEvidence()

        with patch("quodeq.analysis._loops.run_dimension_incremental", side_effect=fake_runner):
            result = run_incremental_loop(
                cfg, ["security", "reliability", "maintainability"], _ctx(3),
                process_fn=MagicMock(),
                log_result_fn=lambda *a: None,
            )
        assert seen == ["security", "reliability", "maintainability"]
        assert set(result) == {"security", "maintainability"}

    def test_diagnostic_log_lines_are_emitted(self):
        cfg = _config()
        with patch("quodeq.analysis._loops.run_dimension_incremental", return_value=_FakeEvidence()), \
             patch("quodeq.analysis._loops.log_info") as mock_log:
            run_incremental_loop(
                cfg, ["security", "flexibility"], _ctx(2),
                process_fn=MagicMock(),
                log_result_fn=lambda *a: None,
            )
        messages = [c.args[0] for c in mock_log.call_args_list]
        assert any("incremental: 2 dim(s) to process: security, flexibility" in m for m in messages)
        assert any("entering iteration 1/2 for security" in m for m in messages)
        assert any("completed iteration 1/2 for security" in m for m in messages)
        assert any("entering iteration 2/2 for flexibility" in m for m in messages)
        assert any("completed iteration 2/2 for flexibility" in m for m in messages)
        assert any("incremental finished: processed 2 of 2 dim(s)" in m for m in messages)


# ---------------------------------------------------------------------------
# Regression test: the exact production bug shape
# ---------------------------------------------------------------------------

class TestProductionBugRegression:
    """Pins down the run f7768d55 incident: usability's queue completed,
    the scoring callback raised BrokenPipeError, the loop bailed before
    flexibility could iterate, and the lifecycle promoted the half-done
    state to ``done`` — both usability's eval and flexibility entirely
    were silently lost.
    """

    def test_usability_callback_dying_does_not_skip_flexibility(self):
        cfg = _config()
        attempted: list[str] = []
        scored: list[str] = []

        def fake_runner(_c, dim, _i, _ctx):
            attempted.append(dim)
            return _FakeEvidence(files_read=979 if dim == "usability" else 22)

        def scoring_callback(dim, _ev):
            # In production, this callback writes evaluation/{dim}.json AND
            # logs to stdout — the latter dies once the dashboard parent pipe
            # closes.
            scored.append(dim)
            if dim == "usability":
                raise BrokenPipeError("Broken pipe")

        with patch("quodeq.analysis._loops.run_dimension_incremental", side_effect=fake_runner):
            result = run_incremental_loop(
                cfg,
                ["security", "reliability", "maintainability", "performance", "usability", "flexibility"],
                _ctx(6),
                process_fn=MagicMock(),
                log_result_fn=lambda *a: None,
                on_dimension_done=scoring_callback,
            )

        # All six dims attempted, including flexibility which was the missing one in prod.
        assert attempted == [
            "security", "reliability", "maintainability", "performance",
            "usability", "flexibility",
        ]
        # Scoring callback fired for first 4 + usability (raised) + flexibility
        # (post-fix continues despite usability's failure).
        assert scored == [
            "security", "reliability", "maintainability", "performance",
            "usability", "flexibility",
        ]
        # All six in result — the evidence was captured even though usability's
        # callback raised.
        assert set(result) == {
            "security", "reliability", "maintainability", "performance",
            "usability", "flexibility",
        }
