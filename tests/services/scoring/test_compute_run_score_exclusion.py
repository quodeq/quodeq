"""compute_run_score excludes circuit-breaker-interrupted dimensions from the
overall grade, but leaves other partial reasons (time_limit, ...) counting."""
from __future__ import annotations

from quodeq.services.scoring.projector_scoring import compute_run_score


def test_excludes_failure_streak_dim_from_overall():
    rows = [
        {"dimension": "security", "score": 6.0, "grade": "Adequate", "exit_reason": None},
        {"dimension": "flexibility", "score": 9.5, "grade": "Exemplary",
         "exit_reason": "failure_streak"},
    ]
    result = compute_run_score(rows)
    assert result["score"] == 6.0  # flexibility (9.5) excluded from the mean


def test_time_limit_dim_still_counts():
    rows = [
        {"dimension": "security", "score": 6.0, "grade": "Adequate", "exit_reason": None},
        {"dimension": "usability", "score": 8.0, "grade": "Good",
         "exit_reason": "time_limit"},
    ]
    result = compute_run_score(rows)
    assert result["score"] == 7.0  # (6.0 + 8.0) / 2 -- time_limit is NOT excluded
