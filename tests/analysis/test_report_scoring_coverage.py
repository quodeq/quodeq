"""Tests for analysis._report_scoring — score/grade conversion and lookup building."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from quodeq.analysis._report_scoring import (
    build_score_lookup,
    extract_scores,
    grade_from_score,
)


# ---------------------------------------------------------------------------
# grade_from_score
# ---------------------------------------------------------------------------

class TestGradeFromScore:
    def test_none_returns_none(self):
        assert grade_from_score(None) is None

    def test_empty_string_returns_none(self):
        assert grade_from_score("") is None

    def test_valid_score(self):
        grade = grade_from_score("8/10")
        assert grade is not None
        assert isinstance(grade, str)

    def test_decimal_score(self):
        grade = grade_from_score("7.5/10")
        assert grade is not None

    def test_no_match_returns_none(self):
        assert grade_from_score("N/A") is None

    def test_perfect_score(self):
        grade = grade_from_score("10/10")
        assert grade is not None

    def test_zero_score(self):
        grade = grade_from_score("0/10")
        assert grade is not None


# ---------------------------------------------------------------------------
# build_score_lookup
# ---------------------------------------------------------------------------

class TestBuildScoreLookup:
    def test_empty_dict(self):
        assert build_score_lookup({}) == {}

    def test_dict_values(self):
        per_principle = {
            "auth": {"displayName": "Authentication", "finalScore": 8.0},
            "log": {"display_name": "Logging", "final_score": 7.0},
        }
        lookup = build_score_lookup(per_principle)
        assert "Authentication" in lookup
        assert "Logging" in lookup

    def test_dataclass_values(self):
        @dataclass
        class FakeScore:
            display_name: str = "Auth"
            final_score: float = 9.0
            grade: str = "A+"

        per_principle = {"auth": FakeScore()}
        lookup = build_score_lookup(per_principle)
        # to_camel_dict converts display_name -> displayName
        assert "Auth" in lookup

    def test_skips_items_without_name(self):
        per_principle = {"x": {"finalScore": 5.0}}  # no displayName or display_name
        lookup = build_score_lookup(per_principle)
        assert lookup == {}


# ---------------------------------------------------------------------------
# extract_scores
# ---------------------------------------------------------------------------

class TestExtractScores:
    def test_none_returns_empty(self):
        princ, overall = extract_scores(None)
        assert princ == {}
        assert overall == {}

    def test_empty_dict_returns_empty(self):
        princ, overall = extract_scores({})
        assert princ == {}
        assert overall == {}

    def test_dict_input(self):
        scores = {
            "principles": {"auth": {"finalScore": 8.0}},
            "overall": {"weightedScore": 8.0, "grade": "A"},
        }
        princ, overall = extract_scores(scores)
        assert "auth" in princ
        assert overall["weightedScore"] == 8.0

    def test_scoring_result_input(self):
        @dataclass
        class FakeOverall:
            weighted_score: float = 7.5
            grade: str = "B+"

        @dataclass
        class FakeScoringResult:
            principles: dict = None
            overall: object = None

        result = FakeScoringResult(
            principles={"auth": {"finalScore": 9.0}},
            overall=FakeOverall(),
        )
        princ, overall = extract_scores(result)
        assert "auth" in princ
        assert "weightedScore" in overall or "weighted_score" in overall

    def test_scoring_result_with_none_overall(self):
        @dataclass
        class FakeScoringResult:
            principles: dict = None
            overall: object = None

        result = FakeScoringResult(principles={"a": {}}, overall=None)
        princ, overall = extract_scores(result)
        assert princ == {"a": {}}
        assert overall == {}
