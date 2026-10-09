"""Tests for the four-stage curve on requirement masses."""
from __future__ import annotations

import math

from quodeq.core.scoring.internals import (
    clamp_principle_score, compliance_dampening, compliance_lift, drop_grade,
    principle_score_and_grade, principle_stages, score_to_grade_label,
    severity_grade_floor, violation_base, violation_ceiling, weight_as_multiplier,
)
from quodeq.core.scoring.constants import MAX_PENALTY_MULTIPLIER
from quodeq.core.scoring.mass import principle_mass, requirement_rows, spread
from quodeq.core.scoring.params import DEFAULT_PARAMS

K = DEFAULT_PARAMS.base_k
W = DEFAULT_PARAMS.severity_weight


def _mass(violations, compliance=(), files=1000, classes=None):
    return principle_mass(requirement_rows(list(violations), list(compliance)), files, classes or {}, params=DEFAULT_PARAMS)


class TestViolationBase:
    def test_no_mass_returns_ten(self):
        assert violation_base(0.0, params=DEFAULT_PARAMS) == 10.0

    def test_one_isolated_critical_caps_near_seven_and_a_half(self):
        wv = W["critical"] * spread(1, 4000)
        assert 7.4 < violation_base(wv, params=DEFAULT_PARAMS) < 7.6

    def test_formula(self):
        assert math.isclose(violation_base(12.5, params=DEFAULT_PARAMS), 10 / (1 + K * 12.5))


class TestComplianceLift:
    def test_zero_when_no_compliance_or_no_violations(self):
        assert compliance_lift(0.0, 5.0, params=DEFAULT_PARAMS) == 0.0
        assert compliance_lift(5.0, 0.0, params=DEFAULT_PARAMS) == 0.0

    def test_formula_and_monotone(self):
        a = compliance_lift(3.0, 3.0, params=DEFAULT_PARAMS)
        b = compliance_lift(9.0, 3.0, params=DEFAULT_PARAMS)
        assert math.isclose(a, 0.5 ** DEFAULT_PARAMS.lift_compress)
        assert b > a


class TestCeilingAndFloor:
    def test_ceiling(self):
        assert violation_ceiling(0.0, params=DEFAULT_PARAMS) == 10.0
        assert math.isclose(violation_ceiling(7.0, params=DEFAULT_PARAMS), 10 - 0.5 * math.log2(8))

    def test_floor_by_worst_effective_severity(self):
        assert severity_grade_floor(None, params=DEFAULT_PARAMS) == 10.0
        assert severity_grade_floor("minor", params=DEFAULT_PARAMS) == 5.0
        assert severity_grade_floor("major", params=DEFAULT_PARAMS) == 3.0
        assert severity_grade_floor("critical", params=DEFAULT_PARAMS) == 0.0

    def test_clamp_ceiling_beats_floor(self):
        # 400 minor rules in every file of a 100-file project: ceiling well under the minor floor
        assert clamp_principle_score(9.0, 2000.0, "minor", params=DEFAULT_PARAMS) == round(violation_ceiling(2000.0, params=DEFAULT_PARAMS), 1)


class TestStages:
    def test_stages_compose(self):
        mass = _mass([{"req": "R-1", "file": "a", "severity": "major"}], [{"req": "R-2", "file": f"c{i}"} for i in range(50)])
        base, lift, raw, final = principle_stages(mass, params=DEFAULT_PARAMS)
        assert math.isclose(base, violation_base(mass.violation_mass, params=DEFAULT_PARAMS))
        assert math.isclose(lift, compliance_lift(mass.compliance_mass, mass.violation_mass, params=DEFAULT_PARAMS))
        assert math.isclose(raw, base + (10 - base) * lift)
        assert final == clamp_principle_score(raw, mass.violation_mass, mass.worst, params=DEFAULT_PARAMS)

    def test_single_minor_in_a_thousand_files_reads_about_nine_point_seven(self):
        mass = _mass([{"req": "R-1", "file": "a", "severity": "minor"}], [{"req": "R-2", "file": f"c{i}"} for i in range(50)])
        final, grade = principle_score_and_grade(mass, params=DEFAULT_PARAMS)
        assert 9.6 <= final <= 9.8 and grade == "Exemplary"

    def test_clean_principle_is_ten(self):
        final, grade = principle_score_and_grade(_mass([], [{"req": "R-1", "file": "a"}]), params=DEFAULT_PARAMS)
        assert (final, grade) == (10.0, "Exemplary")

    def test_class_pins_the_floor_and_the_weight(self):
        rows = [{"req": "S-INT-2", "file": f"f{i}", "severity": "minor"} for i in range(294)]
        unclassed, _ = principle_score_and_grade(_mass(rows, files=2803), params=DEFAULT_PARAMS)
        classed, _ = principle_score_and_grade(_mass(rows, files=2803, classes={"S-INT-2": "critical"}), params=DEFAULT_PARAMS)
        assert classed < unclassed and classed < 5.0  # one critical rule over 294 files: 4.1, not under 3.0


class TestLegacyHelpers:
    def test_dampening_and_drop_grade_unchanged(self):
        assert compliance_dampening({}, {"major": 1}) == MAX_PENALTY_MULTIPLIER
        assert drop_grade("Exemplary", 1) == "Proficient"
        assert weight_as_multiplier("High (x3)") == 3

    def test_grade_labels(self):
        assert score_to_grade_label(9.0) == "Exemplary" and score_to_grade_label(2.9) == "Critical"
