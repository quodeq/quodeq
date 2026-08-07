"""Tests for core scoring formula internals."""
from __future__ import annotations

import math

import pytest

from quodeq.core.scoring.internals import (
    compliance_dampening,
    compliance_lift,
    drop_grade,
    score_to_grade_label,
    severity_grade_floor,
    violation_base,
    violation_ceiling,
    weight_as_multiplier,
)
from quodeq.core.scoring._constants import (
    GRADE_LADDER,
    _BASE_K,
    _CEIL_SCALE,
    _MAX_PENALTY_MULTIPLIER,
)


class TestViolationBase:
    def test_no_violations_returns_ten(self):
        assert violation_base({}) == 10.0

    def test_zero_violations_returns_ten(self):
        assert violation_base({"critical": 0, "major": 0, "minor": 0}) == 10.0

    def test_single_critical_violation(self):
        score = violation_base({"critical": 1})
        # base = 10 / (1 + 0.12 * 4.0) = 10 / 1.48 ~ 6.757
        assert 6.7 < score < 6.8

    def test_single_minor_violation(self):
        score = violation_base({"minor": 1})
        # base = 10 / (1 + 0.12 * 0.25) = 10 / 1.03 ~ 9.709
        assert 9.7 < score < 9.8

    def test_many_violations_approaches_zero(self):
        score = violation_base({"critical": 100})
        assert score < 0.3

    def test_score_in_range(self):
        for counts in [{"critical": 5}, {"major": 10}, {"minor": 20}]:
            s = violation_base(counts)
            assert 0.0 <= s <= 10.0


class TestComplianceLift:
    def test_no_compliance_returns_zero(self):
        assert compliance_lift({}, {"critical": 1}) == 0.0

    def test_no_violations_returns_zero(self):
        assert compliance_lift({"minor": 5}, {}) == 0.0

    def test_lift_between_zero_and_one(self):
        lift = compliance_lift({"minor": 5}, {"minor": 2})
        assert 0.0 < lift < 1.0

    def test_high_compliance_gives_higher_lift(self):
        low = compliance_lift({"minor": 1}, {"minor": 5})
        high = compliance_lift({"minor": 20}, {"minor": 5})
        assert high > low


class TestViolationCeiling:
    def test_no_violations_returns_ten(self):
        assert violation_ceiling({}) == 10.0

    def test_violations_lower_ceiling(self):
        ceil = violation_ceiling({"critical": 1})
        # ceiling = 10 - log2(1 + 4.0) * 0.5 = 10 - 2.322 * 0.5 ~ 8.839
        assert 8.8 < ceil < 8.9

    def test_many_violations_lower_ceiling_further(self):
        ceil = violation_ceiling({"critical": 50})
        assert ceil < 7.0


class TestSeverityGradeFloor:
    def test_no_violations_returns_ten(self):
        assert severity_grade_floor({}) == 10.0

    def test_critical_floor(self):
        assert severity_grade_floor({"critical": 1}) == 0.0

    def test_major_floor(self):
        assert severity_grade_floor({"major": 1}) == 5.0

    def test_minor_floor(self):
        assert severity_grade_floor({"minor": 1}) == 8.0

    def test_critical_takes_priority(self):
        assert severity_grade_floor({"critical": 1, "major": 5, "minor": 10}) == 0.0


class TestScoreToGradeLabel:
    def test_exemplary(self):
        assert score_to_grade_label(9.5) == "Exemplary"

    def test_good(self):
        assert score_to_grade_label(7.5) == "Good"

    def test_adequate(self):
        assert score_to_grade_label(5.5) == "Adequate"

    def test_poor(self):
        assert score_to_grade_label(3.5) == "Poor"

    def test_critical(self):
        assert score_to_grade_label(2.0) == "Critical"

    def test_zero_is_critical(self):
        assert score_to_grade_label(0.0) == "Critical"

    def test_boundary_nine(self):
        assert score_to_grade_label(9.0) == "Exemplary"

    def test_boundary_seven(self):
        assert score_to_grade_label(7.0) == "Good"


class TestComplianceDampening:
    def test_no_violations_returns_one(self):
        assert compliance_dampening({"minor": 5}, {}) == 1.0

    def test_no_compliance_returns_max_penalty(self):
        assert compliance_dampening({}, {"minor": 5}) == _MAX_PENALTY_MULTIPLIER

    def test_high_ratio_reduces_multiplier(self):
        mult = compliance_dampening({"minor": 30}, {"minor": 5})
        assert mult < 1.0  # High compliance ratio dampens

    def test_low_ratio_increases_multiplier(self):
        mult = compliance_dampening({"minor": 1}, {"minor": 10})
        assert mult >= 1.0  # Low ratio amplifies penalty


class TestDropGrade:
    def test_drop_zero_no_change(self):
        assert drop_grade("Exemplary", 0) == "Exemplary"

    def test_drop_one_from_exemplary(self):
        assert drop_grade("Exemplary", 1) == "Proficient"

    def test_drop_floors_at_insufficient(self):
        assert drop_grade("Exemplary", 100) == "Insufficient"

    def test_invalid_grade_returns_insufficient(self):
        assert drop_grade("Unknown", 0) == "Insufficient"


class TestWeightAsMultiplier:
    def test_triple(self):
        assert weight_as_multiplier("High (x3)") == 3

    def test_double(self):
        assert weight_as_multiplier("Medium (x2)") == 2

    def test_default(self):
        assert weight_as_multiplier("Low") == 1

    def test_no_weight(self):
        assert weight_as_multiplier("") == 1


# --- ScoringParams threading -------------------------------------------------
import dataclasses

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.core.scoring.internals import (
    violation_base as _vb,
    compliance_lift as _cl,
    violation_ceiling as _vc,
    severity_grade_floor as _sgf,
    score_to_grade_label as _stgl,
)


def test_violation_base_with_custom_k():
    params = dataclasses.replace(DEFAULT_PARAMS, base_k=0.5)
    # wv for 1 critical = 4.0 → base = 10/(1+0.5*4) = 3.333...
    assert abs(_vb({"critical": 1}, params=params) - 10.0 / 3.0) < 0.01


def test_violation_base_with_custom_severity_weight():
    params = dataclasses.replace(
        DEFAULT_PARAMS, severity_weight={"critical": 8.0, "major": 1.5, "minor": 0.25},
    )
    # wv = 8.0 → base = 10/(1+0.12*8) = 5.102
    assert abs(_vb({"critical": 1}, params=params) - 5.102) < 0.01


def test_compliance_lift_with_custom_compress():
    params = dataclasses.replace(DEFAULT_PARAMS, lift_compress=1.0)
    # cc=4, wv=4 → raw 0.5, compress 1.0 → 0.5
    assert _cl({"minor": 4}, {"critical": 1}, params=params) == pytest.approx(0.5)


def test_violation_ceiling_with_custom_scale():
    params = dataclasses.replace(DEFAULT_PARAMS, ceil_scale=1.0)
    # wv=4 → ceiling = 10 - log2(5)*1.0 = 7.678
    assert abs(_vc({"critical": 1}, params=params) - 7.678) < 0.01


def test_severity_grade_floor_with_custom_floors():
    params = dataclasses.replace(DEFAULT_PARAMS, floor_minor=6.0, floor_major=4.0)
    assert _sgf({"minor": 3}, params=params) == 6.0
    assert _sgf({"major": 1}, params=params) == 4.0
    assert _sgf({"critical": 1}, params=params) == 0.0


def test_score_to_grade_label_with_custom_thresholds():
    params = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=(
        (9.5, "Exemplary"), (8.0, "Good"), (6.0, "Adequate"), (4.0, "Poor"),
    ))
    assert _stgl(9.4, params=params) == "Good"
    assert _stgl(5.0, params=params) == "Poor"
    assert _stgl(3.9, params=params) == "Critical"
