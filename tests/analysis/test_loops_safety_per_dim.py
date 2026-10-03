"""Safety properties of run_per_dimension_loop.

Split from test_loops_safety.py: a broken pipe (or any unexpected
exception) raised by the per-dim runner *or* by the result/scoring
callback must not drop subsequent iterations on the floor. Shared
helpers live in tests/analysis/_loops_safety_fixtures.py.
"""
from __future__ import annotations

from quodeq.analysis._loops import LoopDeps, run_per_dimension_loop
from quodeq.data.fs.dimensions_state_store import read_dimensions

from tests.analysis._loops_safety_fixtures import _FakeEvidence, _config, _ctx, _runner_from


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
            LoopDeps(runner=_runner_from(process_fn), on_dimension_done=on_done),
        )
        # All three dims iterated despite usability's callback raising.
        assert seen_dims == ["security", "usability", "flexibility"]
        # Result still includes usability (we kept the evidence).
        assert set(result) == {"security", "usability", "flexibility"}
        # Callback fired for all three, and usability was retried once.
        assert callback_calls == ["security", "usability", "usability", "flexibility"]

    def test_callback_recognized_exception_does_not_drop_subsequent_dims(self):
        """finalize_dim_result's except narrows to (OSError, ValueError,
        KeyError, TypeError, ArithmeticError) -- the shapes _score_dimension's
        write path can actually raise. One of those from the callback must
        still log and let the loop continue, exactly like the old bare
        ``except Exception`` did."""
        cfg = _config()
        seen: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen.append(dim)
            return _FakeEvidence()

        def on_done(dim, _ev):
            if dim == "reliability":
                raise KeyError("boom")

        result = run_per_dimension_loop(
            cfg, ["security", "reliability", "performance"], _ctx(3),
            LoopDeps(runner=_runner_from(process_fn), on_dimension_done=on_done),
        )
        assert seen == ["security", "reliability", "performance"]
        assert set(result) == {"security", "reliability", "performance"}

    def test_callback_exception_outside_the_narrowed_types_is_isolated_per_dimension(
        self, tmp_path, recording_log,
    ):
        """An exception the callback's contract doesn't name (a real bug, not
        a recognized I/O/data failure) is no longer swallowed by
        finalize_dim_result's own narrowed catch -- but it must not abort the
        whole evaluation run either. run_per_dimension_loop isolates the
        *whole* one-dimension step (dispatch + finalize) at the
        loop-iteration boundary: a warning with the traceback is recorded,
        the loop's own bookkeeping treats the dimension as skipped (the
        on_error path calls the same ``_skip_dim`` the runner-failure path
        uses), and the loop moves on to the next dimension.

        ``finalize_dim_result`` writes the dim's DONE state *before* invoking
        the callback (so the DONE-marked evidence survives a callback bug),
        and DONE is a terminal state in the dim state machine (no
        DONE -> INCOMPLETE transition exists) -- so ``_skip_dim``'s own
        state write is rejected as illegal and safely swallowed, and
        dimensions.json still reads "done" for security. That rejection
        itself is observable as a second, distinct warning.
        """
        cfg = _config()
        cfg.work_dir = tmp_path
        cfg.src = tmp_path
        seen: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen.append(dim)
            return _FakeEvidence()

        def on_done(dim, _ev):
            if dim == "security":
                raise AttributeError("not a narrowed type")

        result = run_per_dimension_loop(
            cfg, ["security", "reliability"], _ctx(2),
            LoopDeps(
                runner=_runner_from(process_fn), on_dimension_done=on_done, log=recording_log,
            ),
        )

        # Both dimensions attempted -- the run completed instead of aborting.
        assert seen == ["security", "reliability"]
        assert "reliability" in result

        entry = read_dimensions(tmp_path)["dimensions"]["security"]
        assert entry["state"] == "done"  # DONE is terminal; see docstring above.

        traceback_warnings = [
            m for m in recording_log.warning_messages if "Traceback (most recent call last)" in m
        ]
        assert traceback_warnings, recording_log.warning_messages
        assert "AttributeError: not a narrowed type" in traceback_warnings[0]

        rejected_transition_warnings = [
            m for m in recording_log.warning_messages if "dim-state transition rejected" in m
        ]
        assert rejected_transition_warnings, recording_log.warning_messages
        assert "done -> incomplete not permitted" in rejected_transition_warnings[0]

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
            LoopDeps(runner=_runner_from(process_fn)),
        )
        # Both iterations attempted; security skipped, reliability succeeds.
        assert seen == ["security", "reliability"]
        assert "security" not in result
        assert "reliability" in result

    def test_unexpected_exception_is_isolated_and_the_traceback_is_logged(self, recording_log):
        cfg = _config()
        seen: list[str] = []

        def process_fn(_c, dim, _i, _ctx):
            seen.append(dim)
            if dim == "security":
                raise AttributeError("boom")
            return _FakeEvidence()

        result = run_per_dimension_loop(
            cfg, ["security", "reliability"], _ctx(2),
            LoopDeps(runner=_runner_from(process_fn), log=recording_log),
        )
        assert seen == ["security", "reliability"]
        assert "security" not in result
        assert "reliability" in result
        matching = [m for m in recording_log.warning_messages if "failed" in m]
        assert matching, recording_log.warning_messages
        assert "Traceback (most recent call last)" in matching[0]
        assert "AttributeError: boom" in matching[0]
        # The boundary covers dispatch + finalize, not dispatch alone, so its
        # label must say "step" -- "dispatch" alone would mislead a reader
        # into thinking the finalize half was untouched.
        assert "security step" in matching[0]
        assert "security dispatch" not in matching[0]

    def test_diagnostic_log_lines_are_emitted(self, recording_log):
        cfg = _config()
        run_per_dimension_loop(
            cfg, ["a", "b"], _ctx(2),
            LoopDeps(runner=_runner_from(lambda *a: _FakeEvidence()), log=recording_log),
        )
        messages = recording_log.info_messages
        # Loop start banner
        assert any("per-dimension: 2 dim(s) to process: a, b" in m for m in messages)
        # Per-iteration entry + completion
        assert any("entering iteration 1/2 for a" in m for m in messages)
        assert any("completed iteration 1/2 for a" in m for m in messages)
        assert any("entering iteration 2/2 for b" in m for m in messages)
        assert any("completed iteration 2/2 for b" in m for m in messages)
        # Final summary
        assert any("per-dimension finished: processed 2 of 2 dim(s)" in m for m in messages)
