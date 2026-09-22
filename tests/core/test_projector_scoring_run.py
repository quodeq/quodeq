"""Unit tests for canonical projector_scoring — compute_dimension_score and
compute_run_score.

Split from test_projector_scoring.py.
"""
from __future__ import annotations

from quodeq.core.scoring.projector_scoring import compute_dimension_score, compute_run_score


def test_compute_dimension_score_averages_principle_scores() -> None:
    p1 = {"principle_id": "P1", "score": 6.0, "grade": "C", "finding_count": 1, "dismissed_count": 0}
    p2 = {"principle_id": "P2", "score": 8.0, "grade": "B", "finding_count": 1, "dismissed_count": 0}

    result = compute_dimension_score(dimension="Security", principle_grades=[p1, p2])

    assert result["dimension"] == "Security"
    assert result["score"] == 7.0


def test_compute_dimension_score_skips_insufficient_principles() -> None:
    p1 = {"principle_id": "P1", "score": None, "grade": "Insufficient", "finding_count": 0, "dismissed_count": 0}
    p2 = {"principle_id": "P2", "score": 8.0, "grade": "B", "finding_count": 1, "dismissed_count": 0}

    result = compute_dimension_score(dimension="Security", principle_grades=[p1, p2])

    assert result["score"] == 8.0


def test_compute_dimension_score_all_insufficient_returns_none() -> None:
    p1 = {"principle_id": "P1", "score": None, "grade": "Insufficient", "finding_count": 0, "dismissed_count": 0}

    result = compute_dimension_score(dimension="Security", principle_grades=[p1])

    assert result["score"] is None
    assert result["grade"] == "Insufficient"


def test_compute_run_score_averages_dimension_scores() -> None:
    d1 = {"dimension": "Security", "score": 7.0, "grade": "B-"}
    d2 = {"dimension": "Reliability", "score": 9.0, "grade": "A"}

    result = compute_run_score([d1, d2])

    assert result["score"] == 8.0


def test_compute_run_score_empty_returns_none() -> None:
    result = compute_run_score([])
    assert result == {"score": None, "grade": None}


def test_compute_run_score_skips_null_scores() -> None:
    d1 = {"dimension": "Security", "score": 8.0, "grade": "A-"}
    d2 = {"dimension": "Reliability", "score": None, "grade": "Insufficient"}

    result = compute_run_score([d1, d2])

    assert result["score"] == 8.0  # only Security counts
