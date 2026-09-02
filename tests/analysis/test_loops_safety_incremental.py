"""Safety properties of run_incremental_loop.

Split from test_loops_safety.py: same broken-pipe/exception safety
guarantee as the per-dimension loop, pinned on the incremental path
(which is what the production run was using when usability +
flexibility got dropped together). Shared helpers live in
tests/analysis/_loops_safety_fixtures.py.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.analysis._loops import run_incremental_loop

from tests.analysis._loops_safety_fixtures import _FakeEvidence, _config, _ctx, _runner_from


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

        def log_result(_ev, dim, _i, _t, **_):
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

    def test_diagnostic_log_lines_are_emitted(self, recording_log):
        cfg = _config()
        with patch("quodeq.analysis._loops._log_dimension_result"):
            run_incremental_loop(
                cfg, ["security", "flexibility"], _ctx(2),
                runner=_runner_from(lambda *a: _FakeEvidence()),
                log=recording_log,
            )
        messages = recording_log.info_messages
        assert any("incremental: 2 dim(s) to process: security, flexibility" in m for m in messages)
        assert any("entering iteration 1/2 for security" in m for m in messages)
        assert any("completed iteration 1/2 for security" in m for m in messages)
        assert any("entering iteration 2/2 for flexibility" in m for m in messages)
        assert any("completed iteration 2/2 for flexibility" in m for m in messages)
        assert any("incremental finished: processed 2 of 2 dim(s)" in m for m in messages)
