"""Backlog-aware dimension order + per-dimension deadline slices.

The dim loop is sequential under one run-wide deadline and only caches
files that finished, so truncation always lands on the last dimension and
that dimension's backlog compounds run after run. These tests pin the two
counter-measures: biggest backlog first, and a per-dimension slice of the
remaining budget.

Fakes come from tests/analysis/_loops_safety_fixtures.py (same config stub
and runner adapter the other loop tests use).
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import DEFAULT, MagicMock, patch

import pytest

from quodeq.analysis._dim_order import _dimension_deadline, _order_by_backlog
from quodeq.analysis._loops import LoopDeps, run_incremental_loop
from quodeq.analysis._types import AnalysisOptions, RunConfig
from quodeq.shared import cancellation

from tests.analysis._loops_safety_fixtures import _FakeEvidence, _config, _ctx, _runner_from

_CONFIGURED = ["security", "reliability", "clean-architecture"]
_ESTIMATES = {
    "security": {"count": 187, "reason": "incremental"},
    "reliability": {"count": 187, "reason": "incremental"},
    "clean-architecture": {"count": 806, "reason": "incremental"},
}
_PIPELINE_SEAMS = ("run_incremental_loop", "run_per_dimension_loop",
                   "load_analysis_context", "_persist_dim_estimates", "emit_marker")


class TestOrderByBacklog:
    def test_biggest_backlog_first_ties_keep_configured_order(self):
        ordered, counts = _order_by_backlog(_CONFIGURED, _ESTIMATES)
        assert ordered == ["clean-architecture", "security", "reliability"]
        assert counts == {"security": 187, "reliability": 187, "clean-architecture": 806}

    def test_logs_one_line_when_the_order_changes(self, recording_log):
        _order_by_backlog(_CONFIGURED, _ESTIMATES, log=recording_log)
        lines = [m for m in recording_log.info_messages if "pending backlog" in m]
        assert lines == [
            "[loop] dimension order by pending backlog: "
            "clean-architecture (806), security (187), reliability (187)",
        ]

    def test_no_log_when_the_order_is_unchanged(self, recording_log):
        already = ["clean-architecture", "security", "reliability"]
        _order_by_backlog(already, _ESTIMATES, log=recording_log)
        assert not [m for m in recording_log.info_messages if "pending backlog" in m]

    @pytest.mark.parametrize("reason", ["full", "diff", "first-run", "empty"])
    def test_no_reorder_when_any_reason_is_not_incremental(self, reason):
        estimates = {**_ESTIMATES, "clean-architecture": {"count": 806, "reason": reason}}
        ordered, counts = _order_by_backlog(_CONFIGURED, estimates)
        assert ordered == _CONFIGURED
        assert counts is None

    @pytest.mark.parametrize("estimates", [None, {}, {"security": {"count": 1, "reason": "incremental"}}])
    def test_no_reorder_when_estimates_are_missing(self, estimates):
        ordered, counts = _order_by_backlog(_CONFIGURED, estimates)
        assert ordered == _CONFIGURED
        assert counts is None

    def test_no_reorder_when_an_estimate_is_not_a_mapping(self):
        # _persist_dim_estimates is patched to a MagicMock in several pipeline
        # tests; its .get() returns a Mock, which must not be ranked.
        ordered, counts = _order_by_backlog(_CONFIGURED, MagicMock())
        assert ordered == _CONFIGURED
        assert counts is None

    def test_negative_counts_clamp_to_zero(self):
        estimates = {**_ESTIMATES, "security": {"count": -5, "reason": "incremental"}}
        _ordered, counts = _order_by_backlog(_CONFIGURED, estimates)
        assert counts["security"] == 0


class TestDimensionDeadline:
    def test_slice_is_proportional_to_what_is_left_after_the_reserves(self):
        # 2 dims still to come after this one -> 120s reserved, 880s split.
        got = _dimension_deadline(0.0, 1000.0, [806, 187, 187], 3)
        assert got == pytest.approx(806 / 1180 * 880)

    def test_equal_shares_when_counts_are_unknown(self):
        assert _dimension_deadline(0.0, 900.0, None, 3) == pytest.approx(780 / 3)

    def test_equal_shares_when_every_count_is_zero(self):
        assert _dimension_deadline(0.0, 900.0, [0, 0, 0], 3) == pytest.approx(780 / 3)

    def test_last_dimension_gets_the_whole_remaining_budget(self):
        assert _dimension_deadline(500.0, 1000.0, [187], 1) == pytest.approx(1000.0)

    def test_never_later_than_the_run_deadline(self):
        assert _dimension_deadline(0.0, 100.0, [5], 1) <= 100.0
        assert _dimension_deadline(0.0, 100.0, [5, 0], 2) <= 100.0

    def test_spent_budget_returns_the_run_deadline(self):
        # now past the run deadline: the loop's own guard must still fire.
        assert _dimension_deadline(1001.0, 1000.0, [806, 187], 2) == 1000.0


class TestDimensionDeadlineFloor:
    """The steady state this fix produces is one backlogged dim and the rest
    fully cached. A pure proportional split hands the heavy dim 100% of the
    budget, and the zero-backlog dims -- which only need seconds to replay
    cache entries, write evidence and score -- get skipped by the loop's
    deadline guard. Each remaining dim keeps a floor.
    """

    def test_zero_backlog_dims_keep_their_floor(self):
        got = _dimension_deadline(0.0, 1000.0, [806, 0, 0], 3)
        assert got <= 1000.0 - 2 * 60.0

    def test_a_zero_count_dim_still_gets_the_floor(self):
        # share is 0 here; without the floor the slice would land on `now`
        # and the loop's guard would skip the dim outright.
        assert _dimension_deadline(0.0, 1000.0, [0, 806], 2) == pytest.approx(60.0)

    def test_budget_smaller_than_the_reserves_degrades_to_equal_shares(self):
        # 90s for 3 dims can't reserve 60s each.
        assert _dimension_deadline(0.0, 90.0, [806, 0, 0], 3) == pytest.approx(30.0)


class TestIncrementalLoopDeadlineSlices:
    def test_slices_advance_toward_the_run_deadline_and_are_restored(self, monkeypatch):
        clock = [0.0]
        # _loop_steps and _dim_order both do `import time`, so one patch of
        # the shared module attribute covers the loop guard and the slicer.
        monkeypatch.setattr("quodeq.analysis._loop_steps.time.monotonic", lambda: clock[0])
        cfg = _config()
        cfg.options.deadline_at = 1000.0
        seen: list[tuple[str, float]] = []

        def fake_runner(config, dim, _idx, _ctx):
            seen.append((dim, config.options.deadline_at))
            clock[0] = config.options.deadline_at  # the dim burns its whole slice
            return _FakeEvidence()

        with patch("quodeq.analysis._loop_steps._log_dimension_result"):
            run_incremental_loop(
                cfg, ["clean-architecture", "security", "reliability"], _ctx(3),
                LoopDeps(runner=_runner_from(fake_runner)),
                dim_counts={"clean-architecture": 806, "security": 187, "reliability": 187},
            )

        assert [dim for dim, _ in seen] == ["clean-architecture", "security", "reliability"]
        deadlines = [deadline for _, deadline in seen]
        assert deadlines == sorted(deadlines)
        assert all(deadline <= 1000.0 for deadline in deadlines)
        assert deadlines[0] == pytest.approx(806 / 1180 * 880)
        assert deadlines[-1] == pytest.approx(1000.0)
        assert cfg.options.deadline_at == 1000.0

    def test_unlimited_budget_sets_no_per_dim_deadline(self):
        cfg = _config()  # deadline_at is None
        seen: list = []

        def fake_runner(config, _dim, _idx, _ctx):
            seen.append(config.options.deadline_at)
            return _FakeEvidence()

        with patch("quodeq.analysis._loop_steps._log_dimension_result"):
            run_incremental_loop(
                cfg, ["security", "reliability"], _ctx(2),
                LoopDeps(runner=_runner_from(fake_runner)),
                dim_counts={"security": 187, "reliability": 806},
            )

        assert seen == [None, None]
        assert cfg.options.deadline_at is None

    def test_equal_slices_when_counts_are_unavailable(self, monkeypatch):
        clock = [0.0]
        monkeypatch.setattr("quodeq.analysis._loop_steps.time.monotonic", lambda: clock[0])
        cfg = _config()
        cfg.options.deadline_at = 90.0
        seen: list[float] = []

        def fake_runner(config, _dim, _idx, _ctx):
            seen.append(config.options.deadline_at)
            clock[0] = config.options.deadline_at
            return _FakeEvidence()

        with patch("quodeq.analysis._loop_steps._log_dimension_result"):
            run_incremental_loop(
                cfg, ["a", "b", "c"], _ctx(3), LoopDeps(runner=_runner_from(fake_runner)),
            )

        # No counts -> three equal 30s slices of the 90s budget.
        assert seen == [pytest.approx(30.0), pytest.approx(60.0), pytest.approx(90.0)]

    def test_deadline_restored_when_the_loop_breaks_early(self):
        cfg = _config()
        run_deadline = time.monotonic() + 1000.0  # real clock: the loop guard reads it
        cfg.options.deadline_at = run_deadline
        seen: list[str] = []

        def fake_runner(_config, dim, _idx, _ctx):
            seen.append(dim)
            cancellation.request_cancel()  # breaker trip during the first dim
            return _FakeEvidence()

        with patch("quodeq.analysis._loop_steps._log_dimension_result"):
            run_incremental_loop(
                cfg, ["clean-architecture", "security"], _ctx(2),
                LoopDeps(runner=_runner_from(fake_runner)),
                dim_counts={"clean-architecture": 806, "security": 187},
            )

        assert seen == ["clean-architecture"]  # second dim skipped by the guard
        assert cfg.options.deadline_at == run_deadline

    def test_deadline_restored_when_the_runner_raises(self):
        cfg = _config()
        run_deadline = time.monotonic() + 1000.0
        cfg.options.deadline_at = run_deadline

        def fake_runner(_config, _dim, _idx, _ctx):
            raise KeyboardInterrupt("ctrl-c mid-dimension")

        with patch("quodeq.analysis._loop_steps._log_dimension_result"), \
                pytest.raises(KeyboardInterrupt):
            run_incremental_loop(
                cfg, ["clean-architecture", "security"], _ctx(2),
                LoopDeps(runner=_runner_from(fake_runner)),
                dim_counts={"clean-architecture": 806, "security": 187},
            )

        assert cfg.options.deadline_at == run_deadline


@contextmanager
def _patched_run(estimates):
    """Run ``_run_dimensions`` with the pipeline seams patched; yield the mocks."""
    with patch.multiple("quodeq.analysis._pipeline",
                        **{seam: DEFAULT for seam in _PIPELINE_SEAMS}) as mocks:
        mocks["load_analysis_context"].return_value = (list(_CONFIGURED), MagicMock())
        mocks["_persist_dim_estimates"].return_value = estimates
        mocks["run_incremental_loop"].return_value = {}

        from quodeq.analysis._pipeline import _run_dimensions
        _run_dimensions(RunConfig(
            src=Path("/tmp/fake-src"), language="python",
            options=AnalysisOptions(incremental=True),
        ))
        yield mocks


class TestPipelineWiring:
    def test_run_dimensions_hands_the_loop_the_backlog_order(self):
        with _patched_run(_ESTIMATES) as mocks:
            args, kwargs = mocks["run_incremental_loop"].call_args
            assert args[1] == ["clean-architecture", "security", "reliability"]
            assert kwargs["dim_counts"] == {
                "security": 187, "reliability": 187, "clean-architecture": 806,
            }
            # The setup marker advertises the order the run will actually use.
            assert mocks["emit_marker"].call_args.kwargs["dimensions"] == [
                "clean-architecture", "security", "reliability",
            ]

    def test_run_dimensions_keeps_configured_order_without_estimates(self):
        with _patched_run(None) as mocks:
            args, kwargs = mocks["run_incremental_loop"].call_args
            assert args[1] == _CONFIGURED
            assert kwargs["dim_counts"] is None
