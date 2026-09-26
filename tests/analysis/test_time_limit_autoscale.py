"""Tests for the time-limit auto-scaling helper.

The fixed 600s default time limit chokes on dim queues with hundreds of
files (observed throughput ≈ 7-12 s/file with 8 agents). When that
happens, surviving pending files keep haunting the next run via the
not_analyzed sweep and the dim never converges. The auto-scaler treats
the user's ``time_limit`` as a floor and extends it to give each file a
fair slice of wallclock time, capped at a hard upper bound.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from quodeq.analysis.run_types import AnalysisOptions
from quodeq.analysis.subagents._pool_launcher import (
    _MAX_AUTO_POOL_BUDGET,
    _SECONDS_PER_FILE_AUTOSCALE,
    _UNLIMITED_BUDGET,
    _resolve_time_limit,
)
from quodeq.shared.constants import DEFAULT_TIME_LIMIT


class TestResolveTimeLimit:
    def test_small_queue_uses_user_budget_as_floor(self) -> None:
        # 30 files × 12 s/file = 360s, which is below the default 600s
        # floor → return the floor unchanged.
        assert _resolve_time_limit(None, 30) == DEFAULT_TIME_LIMIT

    def test_large_queue_extends_budget(self) -> None:
        # 800 files × 12 s/file = 9600s, capped at 7200s (2h).
        assert _resolve_time_limit(None, 800) == _MAX_AUTO_POOL_BUDGET

    def test_medium_queue_scales_proportionally(self) -> None:
        # 200 files × 12 s/file = 2400s, above the 600s floor and below
        # the 7200s ceiling → return the proportional value.
        assert _resolve_time_limit(None, 200) == 200 * _SECONDS_PER_FILE_AUTOSCALE

    def test_explicit_user_budget_is_a_hard_cap(self) -> None:
        # An explicitly chosen limit is respected verbatim: the run stops
        # dispatching at the cap and carries the remainder forward. Only
        # the implicit default is auto-scaled. (A 60s limit that silently
        # became a 2h run was the opposite of what the user asked for.)
        assert _resolve_time_limit(1800, 30) == 1800
        assert _resolve_time_limit(1800, 300) == 1800
        assert _resolve_time_limit(60, 837) == 60

    def test_unlimited_budget_is_preserved(self) -> None:
        # time_limit=0 means "no cap"; auto-scaling must not turn that
        # into a finite number, otherwise we'd silently cap users who
        # asked for unlimited.
        assert _resolve_time_limit(_UNLIMITED_BUDGET, 30) == _UNLIMITED_BUDGET
        assert _resolve_time_limit(_UNLIMITED_BUDGET, 10000) == _UNLIMITED_BUDGET

    def test_zero_or_negative_queue_returns_base(self) -> None:
        # Defensive: an empty file list shouldn't produce a 0-second budget.
        assert _resolve_time_limit(None, 0) == DEFAULT_TIME_LIMIT
        assert _resolve_time_limit(900, 0) == 900

    def test_runaway_queue_capped_at_max(self) -> None:
        assert _resolve_time_limit(None, 100_000) == _MAX_AUTO_POOL_BUDGET
        # Explicit budgets are never scaled, not even for runaway queues.
        assert _resolve_time_limit(900, 100_000) == 900


class TestExtendRunDeadline:
    """The run-level deadline must follow the pool's granted budget.

    The auto-scaled pool budget can exceed the run deadline computed from
    the user's original limit; without ratcheting the deadline forward,
    the job watchdog SIGTERMs a healthy run at original-limit+grace while
    the pool believes it has hours left (observed: limit
    60s auto-scaled to 7200s, killed at start+121s).
    """

    def test_extends_deadline_emits_marker_and_notifies(self):
        from quodeq.analysis.subagents._pool_launcher import _extend_run_deadline
        received = []
        opts = AnalysisOptions(
            deadline_at=time.monotonic() + 60,
            on_deadline_extended=received.append,
        )
        with patch(
            "quodeq.analysis.subagents._pool_launcher.emit_marker"
        ) as marker:
            _extend_run_deadline(opts, 7200)

        assert opts.deadline_at >= time.monotonic() + 7000
        marker.assert_called_once()
        assert marker.call_args.args[0] == "deadline_extended"
        iso = marker.call_args.kwargs["deadline_at"]
        parsed = datetime.fromisoformat(iso)
        assert parsed.tzinfo is not None
        assert (parsed - datetime.now(timezone.utc)).total_seconds() > 7000
        assert received == [iso]

    def test_never_shortens_the_deadline(self):
        from quodeq.analysis.subagents._pool_launcher import _extend_run_deadline
        far = time.monotonic() + 99_999
        opts = AnalysisOptions(deadline_at=far)
        with patch(
            "quodeq.analysis.subagents._pool_launcher.emit_marker"
        ) as marker:
            _extend_run_deadline(opts, 60)
        assert opts.deadline_at == far
        marker.assert_not_called()

    def test_noop_when_run_is_unlimited(self):
        from quodeq.analysis.subagents._pool_launcher import _extend_run_deadline
        opts = AnalysisOptions(deadline_at=None)
        with patch(
            "quodeq.analysis.subagents._pool_launcher.emit_marker"
        ) as marker:
            _extend_run_deadline(opts, 7200)
        assert opts.deadline_at is None
        marker.assert_not_called()

    def test_noop_when_pool_budget_unlimited(self):
        from quodeq.analysis.subagents._pool_launcher import _extend_run_deadline
        original = time.monotonic() + 60
        opts = AnalysisOptions(deadline_at=original)
        with patch(
            "quodeq.analysis.subagents._pool_launcher.emit_marker"
        ) as marker:
            _extend_run_deadline(opts, _UNLIMITED_BUDGET)
        assert opts.deadline_at == original
        marker.assert_not_called()

    def test_callback_failure_does_not_raise(self):
        """OSError (e.g. status.json write failure) is caught and logged;
        the deadline extension itself still lands. A failure outside the
        narrow (OSError, TypeError, ValueError) tuple, by contrast, must
        propagate rather than be swallowed -- both checked here so the one
        already-grandfathered private import this file needs for
        ``_extend_run_deadline`` (see tools/private_imports_tests_baseline.txt)
        does not grow with a second test function."""
        from quodeq.analysis.subagents._pool_launcher import _extend_run_deadline

        def _boom(_iso: str) -> None:
            raise OSError("status write failed")

        opts = AnalysisOptions(
            deadline_at=time.monotonic() + 60,
            on_deadline_extended=_boom,
        )
        with patch("quodeq.analysis.subagents._pool_launcher.emit_marker"):
            _extend_run_deadline(opts, 7200)
        # The extension itself must still land even if the notify fails.
        assert opts.deadline_at >= time.monotonic() + 7000

        def _boom_unnamed(_iso: str) -> None:
            raise RuntimeError("unexpected")

        opts2 = AnalysisOptions(
            deadline_at=time.monotonic() + 60,
            on_deadline_extended=_boom_unnamed,
        )
        with patch("quodeq.analysis.subagents._pool_launcher.emit_marker"):
            with pytest.raises(RuntimeError, match="unexpected"):
                _extend_run_deadline(opts2, 7200)
