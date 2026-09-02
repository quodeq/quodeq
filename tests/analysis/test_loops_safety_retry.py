"""Retry-after-broken-pipe persistence semantics, and the exact production
bug shape (run f7768d55).

Split from test_loops_safety.py. Shared helpers live in
tests/analysis/_loops_safety_fixtures.py.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.analysis._loops import run_incremental_loop, run_per_dimension_loop

from tests.analysis._loops_safety_fixtures import _FakeEvidence, _config, _ctx, _runner_from


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

    def test_per_dim_retry_failure_logs_not_persisted_warning(self, recording_log):
        cfg = _config()

        def always_raises(_dim, _ev):
            raise BrokenPipeError("permanently broken")

        run_per_dimension_loop(
            cfg, ["security"], _ctx(1),
            runner=_runner_from(lambda *a: _FakeEvidence()),
            on_dimension_done=always_raises,
            log=recording_log,
        )
        warn_messages = recording_log.warning_messages
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
        def log_result(_ev, dim, _i, _t, **_):
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
