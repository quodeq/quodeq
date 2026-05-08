"""Tests for core scoring formula internals."""
from __future__ import annotations

import math

import pytest

from quodeq.core.scoring.internals import (
    compliance_dampening,
    compliance_lift,
    density_weighted_sum,
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
        assert severity_grade_floor({"major": 1}) == 3.0

    def test_minor_floor(self):
        assert severity_grade_floor({"minor": 1}) == 5.0

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


class TestDensityWeightedSum:
    def test_empty(self):
        assert density_weighted_sum([], using_taxonomy=True) == 0.0

    def test_single_instance_matches_legacy(self):
        # A single instance per type → log2(2) = 1.0, so the result equals
        # the legacy weighted sum (severity_weight × type_count).
        items = [
            {"severity": "critical", "vt": "A"},
            {"severity": "critical", "vt": "B"},
            {"severity": "major", "vt": "C"},
        ]
        # 2 critical types × 4.0 + 1 major type × 1.5 = 9.5
        assert density_weighted_sum(items, using_taxonomy=True) == pytest.approx(9.5)

    def test_high_instance_density_dominates(self):
        """Many instances of one type weigh more than a single instance — the
        whole point of the density formula."""
        sparse = [{"severity": "critical", "vt": "A"}]
        dense = [{"severity": "critical", "vt": "A"}] * 10
        assert density_weighted_sum(dense, using_taxonomy=True) > density_weighted_sum(sparse, using_taxonomy=True)
        # 10 instances → severity_weight × log2(11) ≈ 4.0 × 3.46 ≈ 13.84
        assert density_weighted_sum(dense, using_taxonomy=True) == pytest.approx(4.0 * math.log2(11))

    def test_skips_taxonomy_items_without_vt(self):
        items = [
            {"severity": "critical", "vt": "A"},
            {"severity": "critical"},  # no vt → skipped in taxonomy mode
        ]
        assert density_weighted_sum(items, using_taxonomy=True) == pytest.approx(4.0 * math.log2(2))


class TestWeightAsMultiplier:
    def test_triple(self):
        assert weight_as_multiplier("High (x3)") == 3

    def test_double(self):
        assert weight_as_multiplier("Medium (x2)") == 2

    def test_default(self):
        assert weight_as_multiplier("Low") == 1

    def test_no_weight(self):
        assert weight_as_multiplier("") == 1
