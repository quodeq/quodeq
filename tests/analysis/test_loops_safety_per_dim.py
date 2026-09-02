"""Safety properties of run_per_dimension_loop.

Split from test_loops_safety.py: a broken pipe (or any unexpected
exception) raised by the per-dim runner *or* by the result/scoring
callback must not drop subsequent iterations on the floor. Shared
helpers live in tests/analysis/_loops_safety_fixtures.py.
"""
from __future__ import annotations

from quodeq.analysis._loops import run_per_dimension_loop

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

    def test_diagnostic_log_lines_are_emitted(self, recording_log):
        cfg = _config()
        run_per_dimension_loop(
            cfg, ["a", "b"], _ctx(2),
            runner=_runner_from(lambda *a: _FakeEvidence()),
            log=recording_log,
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
