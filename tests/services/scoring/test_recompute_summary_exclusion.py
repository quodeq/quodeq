"""recompute_summary keeps a failure_streak dimension out of the overall numeric
average, while still tallying its findings. time_limit dims keep counting."""
from __future__ import annotations

from quodeq.services.scoring._summary import recompute_summary


def _dim(name, score, grade, exit_reason=None, violations=0):
    return {
        "dimension": name,
        "overallScore": f"{score}/10",
        "overallGrade": grade,
        "exitReason": exit_reason,
        "totals": {
            "violationCount": violations, "complianceCount": 0,
            "severity": {"critical": 0, "major": 0, "minor": violations},
        },
    }


def test_failure_streak_dim_excluded_from_average_but_counted_in_totals():
    dims = [
        _dim("security", 6.0, "Adequate", violations=2),
        _dim("flexibility", 9.5, "Exemplary", exit_reason="failure_streak", violations=3),
    ]
    summary = recompute_summary(dims, {})
    assert summary["numericAverage"] == 6.0  # flexibility excluded from the mean
    assert summary["totalViolations"] == 5  # but its findings still tallied
    assert summary["dimensionCount"] == 2


def test_time_limit_dim_still_in_average():
    dims = [
        _dim("security", 6.0, "Adequate"),
        _dim("usability", 8.0, "Good", exit_reason="time_limit"),
    ]
    summary = recompute_summary(dims, {})
    assert summary["numericAverage"] == 7.0
