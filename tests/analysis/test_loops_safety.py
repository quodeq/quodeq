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
    # Default: no run-level deadline (would otherwise be a MagicMock and
    # break the numeric comparison in the loop's deadline guard).
    cfg.options.deadline_at = None
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


def _runner_from(fn):
    """Wrap a process-fn callable (`(cfg, dim, idx, ctx) -> Evidence`) into a
    DimensionRunner-shaped mock so it can be passed as ``runner=``.

    The new signature includes a keyword-only ``emit_log`` that the loops
    pass; tests don't care about it, so we accept and ignore it.
    """
    def _adapter(cfg, dim, idx, ctx, *, emit_log=True):
        return fn(cfg, dim, idx, ctx)

    runner = MagicMock()
    runner.run.side_effect = _adapter
    return runner


# ---------------------------------------------------------------------------
# run_per_dimension_loop
# ---------------------------------------------------------------------------

class TestPerDimLoopSafety:
    def test_callback_broken_pipe_does_not_drop_subsequent_dims(self):
        """The bug we observed: scoring callback writes to closed pipe,
        BrokenPipeError propagates, loop terminates early.

        Post-fix the callback is retried once after stdout/stderr are silenced,
        so usability appears twice in callback_calls (the second invocation
        is the retry that persists the side effects).
        """
        cfg = _config()
        seen_dims: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen_dims.append(dim)
            return _FakeEvidence()

        callback_calls: list[str] = []
        usability_raise_count = {"n": 0}
        def on_done(dim, _ev):
            callback_calls.append(dim)
            if dim == "usability" and usability_raise_count["n"] == 0:
                usability_raise_count["n"] += 1
                raise BrokenPipeError("parent pipe closed")

        result = run_per_dimension_loop(
            cfg, ["security", "usability", "flexibility"], _ctx(3),
            runner=_runner_from(process_fn), on_dimension_done=on_done,
        )
        # All three dims iterated despite usability's callback raising.
        assert seen_dims == ["security", "usability", "flexibility"]
        # Result still includes usability (we kept the evidence).
        assert set(result) == {"security", "usability", "flexibility"}
        # Callback fired for all three, and usability was retried once.
        assert callback_calls == ["security", "usability", "usability", "flexibility"]

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
            runner=_runner_from(process_fn), on_dimension_done=on_done,
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
            runner=_runner_from(process_fn),
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
                runner=_runner_from(lambda *a: _FakeEvidence()),
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

        with patch("quodeq.analysis._loops._log_dimension_result", side_effect=log_result):
            result = run_incremental_loop(
                cfg, ["security", "usability", "flexibility"], _ctx(3),
                runner=_runner_from(fake_runner),
                on_dimension_done=on_done,
            )

        # All three iterated — flexibility ran despite usability's callback dying.
        assert seen == ["security", "usability", "flexibility"]
        # All three results captured (we keep the evidence even when callback fails).
        assert set(result) == {"security", "usability", "flexibility"}
        # log_result_fn raised before on_done was reached for usability, so the
        # retry path invokes on_done for usability after silencing — meaning
        # usability now DOES appear in callback_calls (the persistence retry).
        assert callback_calls == ["security", "usability", "flexibility"]

    def test_unexpected_exception_in_runner_logs_and_continues(self):
        cfg = _config()
        seen: list[str] = []

        def fake_runner(_c, dim, _i, _ctx):
            seen.append(dim)
            if dim == "reliability":
                raise AttributeError("not in catch list")
            return _FakeEvidence()

        with patch("quodeq.analysis._loops._log_dimension_result"):
            result = run_incremental_loop(
                cfg, ["security", "reliability", "maintainability"], _ctx(3),
                runner=_runner_from(fake_runner),
            )
        assert seen == ["security", "reliability", "maintainability"]
        assert set(result) == {"security", "maintainability"}

    def test_diagnostic_log_lines_are_emitted(self):
        cfg = _config()
        with patch("quodeq.analysis._loops._log_dimension_result"), \
             patch("quodeq.analysis._loops.log_info") as mock_log:
            run_incremental_loop(
                cfg, ["security", "flexibility"], _ctx(2),
                runner=_runner_from(lambda *a: _FakeEvidence()),
            )
        messages = [c.args[0] for c in mock_log.call_args_list]
        assert any("incremental: 2 dim(s) to process: security, flexibility" in m for m in messages)
        assert any("entering iteration 1/2 for security" in m for m in messages)
        assert any("completed iteration 1/2 for security" in m for m in messages)
        assert any("entering iteration 2/2 for flexibility" in m for m in messages)
        assert any("completed iteration 2/2 for flexibility" in m for m in messages)
        assert any("incremental finished: processed 2 of 2 dim(s)" in m for m in messages)


# ---------------------------------------------------------------------------
# Retry-after-broken-pipe persistence semantics
# ---------------------------------------------------------------------------

class TestCallbackRetryPersistsSideEffects:
    """Pin down the per-dim run f061b58e bug: security's queue completed,
    the scoring callback raised BrokenPipeError mid-run, the loop swallowed
    it with a misleading "result kept" message but evaluation/security.json
    was never written.

    Post-fix: when a callback raises BrokenPipeError, stdout is silenced and
    the callback is retried once so persistent side effects (the on-disk
    report) actually land.
    """

    def test_per_dim_retry_persists_when_only_first_call_raises(self):
        cfg = _config()
        # Imitate _score_dimension's contract: on success, write a sentinel
        # file. On the first call for the dim, raise BrokenPipeError before
        # the write. On retry, the write succeeds.
        written: list[str] = []
        attempts: dict[str, int] = {}

        def scoring_callback(dim, _ev):
            attempts[dim] = attempts.get(dim, 0) + 1
            if dim == "security" and attempts[dim] == 1:
                raise BrokenPipeError("parent pipe closed mid-write")
            written.append(dim)

        run_per_dimension_loop(
            cfg, ["security", "reliability"], _ctx(2),
            runner=_runner_from(lambda *a: _FakeEvidence()),
            on_dimension_done=scoring_callback,
        )
        # security was retried once; reliability ran straight through.
        assert attempts == {"security": 2, "reliability": 1}
        # Both files written — the bug was that security's write was lost.
        assert written == ["security", "reliability"]

    def test_per_dim_retry_failure_logs_not_persisted_warning(self):
        cfg = _config()

        def always_raises(_dim, _ev):
            raise BrokenPipeError("permanently broken")

        with patch("quodeq.analysis._loops.log_warning") as mock_warn:
            run_per_dimension_loop(
                cfg, ["security"], _ctx(1),
                runner=_runner_from(lambda *a: _FakeEvidence()),
                on_dimension_done=always_raises,
            )
        warn_messages = [c.args[0] for c in mock_warn.call_args_list]
        assert any("retry after broken pipe raised" in m for m in warn_messages), warn_messages
        assert any("NOT persisted" in m for m in warn_messages), warn_messages

    def test_incremental_retry_persists_when_only_first_call_raises(self):
        cfg = _config()
        written: list[str] = []
        attempts: dict[str, int] = {}

        def fake_runner(_c, dim, _i, _ctx):
            return _FakeEvidence()

        # _log_dimension_result raises BrokenPipeError before
        # on_dimension_done is reached on the original try; the retry path
        # then invokes on_dimension_done with stdout silenced.
        def log_result(_ev, dim, _i, _t):
            if dim == "security":
                raise BrokenPipeError("dashboard pipe closed")

        def scoring_callback(dim, _ev):
            attempts[dim] = attempts.get(dim, 0) + 1
            written.append(dim)

        with patch("quodeq.analysis._loops._log_dimension_result", side_effect=log_result):
            run_incremental_loop(
                cfg, ["security", "reliability"], _ctx(2),
                runner=_runner_from(fake_runner),
                on_dimension_done=scoring_callback,
            )

        assert attempts == {"security": 1, "reliability": 1}
        assert written == ["security", "reliability"]


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

        usability_first_call = {"done": False}
        def scoring_callback(dim, _ev):
            # In production, this callback writes evaluation/{dim}.json AND
            # logs to stdout — the latter dies once the dashboard parent pipe
            # closes. Post-fix the loop retries the callback after silencing
            # stdout, so the second call succeeds and persists the write.
            scored.append(dim)
            if dim == "usability" and not usability_first_call["done"]:
                usability_first_call["done"] = True
                raise BrokenPipeError("Broken pipe")

        with patch("quodeq.analysis._loops._log_dimension_result"):
            result = run_incremental_loop(
                cfg,
                ["security", "reliability", "maintainability", "performance", "usability", "flexibility"],
                _ctx(6),
                runner=_runner_from(fake_runner),
                on_dimension_done=scoring_callback,
            )

        # All six dims attempted, including flexibility which was the missing one in prod.
        assert attempted == [
            "security", "reliability", "maintainability", "performance",
            "usability", "flexibility",
        ]
        # Scoring callback fired for first 4, then usability twice (initial raise
        # + retry that persists), then flexibility.
        assert scored == [
            "security", "reliability", "maintainability", "performance",
            "usability", "usability", "flexibility",
        ]
        # All six in result — the evidence was captured even though usability's
        # callback raised.
        assert set(result) == {
            "security", "reliability", "maintainability", "performance",
            "usability", "flexibility",
        }
