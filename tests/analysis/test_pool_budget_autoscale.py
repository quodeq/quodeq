"""Tests for the pool-budget auto-scaling helper.

The fixed 600s default pool budget chokes on dim queues with hundreds of
files (observed throughput ≈ 7-12 s/file with 8 agents). When that
happens, surviving pending files keep haunting the next run via the
not_analyzed sweep and the dim never converges. The auto-scaler treats
the user's ``pool_budget`` as a floor and extends it to give each file a
fair slice of wallclock time, capped at a hard upper bound.
"""
from __future__ import annotations

from quodeq.analysis.subagents._pool_launcher import (
    _MAX_AUTO_POOL_BUDGET,
    _SECONDS_PER_FILE_AUTOSCALE,
    _UNLIMITED_BUDGET,
    _resolve_pool_budget,
)
from quodeq.shared.constants import _DEFAULT_POOL_BUDGET


class TestResolvePoolBudget:
    def test_small_queue_uses_user_budget_as_floor(self) -> None:
        # 30 files × 12 s/file = 360s, which is below the default 600s
        # floor → return the floor unchanged.
        assert _resolve_pool_budget(None, 30) == _DEFAULT_POOL_BUDGET

    def test_large_queue_extends_budget(self) -> None:
        # 800 files × 12 s/file = 9600s, capped at 7200s (2h).
        assert _resolve_pool_budget(None, 800) == _MAX_AUTO_POOL_BUDGET

    def test_medium_queue_scales_proportionally(self) -> None:
        # 200 files × 12 s/file = 2400s, above the 600s floor and below
        # the 7200s ceiling → return the proportional value.
        assert _resolve_pool_budget(None, 200) == 200 * _SECONDS_PER_FILE_AUTOSCALE

    def test_explicit_user_budget_is_floor_not_cap(self) -> None:
        # User wants at least 1800s; queue would only need 600s → keep 1800.
        assert _resolve_pool_budget(1800, 30) == 1800
        # User wants 1800s but queue needs 3600s → extend to 3600.
        assert _resolve_pool_budget(1800, 300) == 300 * _SECONDS_PER_FILE_AUTOSCALE

    def test_unlimited_budget_is_preserved(self) -> None:
        # pool_budget=0 means "no cap"; auto-scaling must not turn that
        # into a finite number, otherwise we'd silently cap users who
        # asked for unlimited.
        assert _resolve_pool_budget(_UNLIMITED_BUDGET, 30) == _UNLIMITED_BUDGET
        assert _resolve_pool_budget(_UNLIMITED_BUDGET, 10000) == _UNLIMITED_BUDGET

    def test_zero_or_negative_queue_returns_base(self) -> None:
        # Defensive: an empty file list shouldn't produce a 0-second budget.
        assert _resolve_pool_budget(None, 0) == _DEFAULT_POOL_BUDGET
        assert _resolve_pool_budget(900, 0) == 900

    def test_runaway_queue_capped_at_max(self) -> None:
        assert _resolve_pool_budget(None, 100_000) == _MAX_AUTO_POOL_BUDGET
        assert _resolve_pool_budget(900, 100_000) == _MAX_AUTO_POOL_BUDGET
