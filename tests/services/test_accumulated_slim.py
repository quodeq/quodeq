"""Accumulated slim reads keep the open-type count the hero shows."""
from __future__ import annotations

from quodeq.core.types import DimensionResult
from quodeq.core.types.finding import Finding
from quodeq.services.accumulated import slim_dimensions


def _violation(req: str | None) -> Finding:
    return Finding(verdict="violation", file="a.py", line=1, req=req, severity="minor")


def test_slim_dimensions_counts_open_types_from_findings() -> None:
    dim = DimensionResult(
        dimension="maintainability",
        violations=[_violation("M-MDF-1"), _violation("M-MDF-1"), _violation("M-ANA-9"), _violation(None)],
        compliance=[_violation("M-REU-1")],
    )
    slim = slim_dimensions([dim])[0]
    assert (slim.violations, slim.compliance, slim.open_types) == ([], [], 2)


def test_slim_dimensions_keeps_a_known_open_types_value() -> None:
    dim = DimensionResult(dimension="security", open_types=7, violations=[_violation("S-1")])
    assert slim_dimensions([dim])[0].open_types == 7
