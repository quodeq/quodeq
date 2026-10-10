# tests/core/scoring/test_mass.py
"""The per-requirement mass: spread by files, cumulative severity, class applied exactly."""
from __future__ import annotations

import math

import pytest

from quodeq.core.scoring.mass import (
    DENOMINATOR_FLOOR, PrincipleMass, finding_key, principle_mass,
    requirement_mass, requirement_rows, spread,
)
from quodeq.core.scoring.params import DEFAULT_PARAMS

W = DEFAULT_PARAMS.severity_weight


def test_spread_zero_files_is_zero():
    assert spread(0, 4000) == 0.0


def test_spread_one_file_in_four_thousand_is_about_one():
    assert math.isclose(spread(1, 4000), 1 + math.log2(1 + 100 / 4000))
    assert 1.03 < spread(1, 4000) < 1.05


def test_spread_one_per_hundred_is_two_and_every_file_is_about_seven_point_seven():
    assert math.isclose(spread(10, 1000), 2.0)
    assert 7.6 < spread(1000, 1000) < 7.8


def test_spread_unknown_project_size_is_one_per_hit_rule():
    """No file count (old runs): spread 1 for any hit rule reproduces the un-spread formula."""
    assert spread(3, 0) == 1.0
    assert spread(0, 0) == 0.0


def test_spread_floors_the_denominator_at_one_hundred_files():
    assert spread(2, 6) == spread(2, DENOMINATOR_FLOOR)


def test_spread_is_scale_invariant():
    assert math.isclose(spread(30, 300), spread(300, 3000))


def test_finding_key_prefers_req_then_vt_then_reason():
    assert finding_key({"req": "M-1", "vt": "x", "reason": "y"}) == "M-1"
    assert finding_key({"vt": "x", "reason": "y"}) == "x"
    assert finding_key({"reason": "y"}) == "y"
    assert finding_key({}) == "unknown"


def test_requirement_rows_keep_the_worst_severity_per_file_and_collapse_repeats():
    rows = requirement_rows(
        [
            {"req": "R-1", "file": "a.py", "severity": "minor"},
            {"req": "R-1", "file": "a.py", "severity": "major"},
            {"req": "R-1", "file": "a.py", "severity": "major"},
            {"req": "R-1", "file": "b.py", "severity": "bogus"},
            {"req": "R-2", "severity": "minor"},
            {"req": "R-2", "severity": "critical"},
        ],
        [{"req": "R-1", "file": "c.py"}, {"req": "R-1", "file": "c.py"}, {"req": "R-3", "file": "d.py"}],
    )
    assert rows.violations["R-1"] == {"a.py": "major", "b.py": "minor"}
    assert rows.violations["R-2"] == {"": "critical"}  # no file: one pseudo-file
    assert rows.compliance == {"R-1": frozenset({"c.py"}), "R-3": frozenset({"d.py"})}


def test_requirement_mass_homogeneous_rule_is_weight_times_spread():
    row = requirement_mass({f"f{i}": "major" for i in range(300)}, 2800, params=DEFAULT_PARAMS)
    assert math.isclose(row.weight, W["major"] * spread(300, 2800))
    assert row.worst == "major"
    assert row.files_at_least == {"minor": 300, "major": 300, "critical": 0}


def test_requirement_mass_mixed_rule_adds_each_level():
    files = {f"f{i}": "minor" for i in range(100)}
    files.update({f"g{i}": "major" for i in range(20)})
    row = requirement_mass(files, 1000, params=DEFAULT_PARAMS)
    expected = W["minor"] * spread(120, 1000) + (W["major"] - W["minor"]) * spread(20, 1000)
    assert math.isclose(row.weight, expected)


def test_mass_uses_the_findings_own_severity():
    rows = requirement_rows([
        {"req": "S-INT-2", "severity": "minor", "file": "a.py"},
        {"req": "S-INT-2", "severity": "major", "file": "b.py"},
    ], [])
    row = principle_mass(rows, 100, params=DEFAULT_PARAMS).violations[0]
    assert row.worst == "major"
    assert row.files_at_least["major"] == 1 and row.files_at_least["minor"] == 2
    assert not hasattr(row, "severity_class")


def test_requirement_mass_one_outlier_adds_one_file_not_the_whole_rule():
    base = {f"f{i}": "minor" for i in range(300)}
    plain = requirement_mass(base, 3000, params=DEFAULT_PARAMS).weight
    outlier = dict(base, f299="critical")
    with_outlier = requirement_mass(outlier, 3000, params=DEFAULT_PARAMS).weight
    one_file_as_critical = (W["major"] - W["minor"]) * spread(1, 3000) + (W["critical"] - W["major"]) * spread(1, 3000)
    assert math.isclose(with_outlier - plain, one_file_as_critical)


def test_principle_mass_sums_rows_and_observation_counts_every_observed_rule():
    rows = requirement_rows(
        [{"req": "R-1", "file": "a", "severity": "major"}, {"req": "R-2", "file": "b", "severity": "minor"}],
        [{"req": "R-2", "file": "c"}, {"req": "R-3", "file": "d"}, {"req": "R-3", "file": "e"}],
    )
    mass = principle_mass(rows, 1000, params=DEFAULT_PARAMS)
    assert isinstance(mass, PrincipleMass)
    assert math.isclose(mass.violation_mass, W["major"] * spread(1, 1000) + W["minor"] * spread(1, 1000))
    assert math.isclose(mass.compliance_mass, spread(1, 1000) + spread(2, 1000))
    assert math.isclose(mass.observation, 2 * spread(1, 1000) + spread(1, 1000) + spread(2, 1000))
    assert mass.worst == "major"
    assert [r.req for r in mass.violations] == ["R-1", "R-2"]
    assert [r.req for r in mass.compliance] == ["R-2", "R-3"]


def test_principle_mass_with_nothing_is_empty():
    mass = principle_mass(requirement_rows([], []), 1000, params=DEFAULT_PARAMS)
    assert (mass.violation_mass, mass.compliance_mass, mass.observation, mass.worst) == (0.0, 0.0, 0.0, None)


@pytest.mark.parametrize("bad", [{"critical": 4.0, "major": 4.0, "minor": 0.25}, {"critical": 4.0, "major": 1.0, "minor": 2.0}])
def test_requirement_mass_rejects_non_increasing_weights(bad):
    import dataclasses
    params = dataclasses.replace(DEFAULT_PARAMS, severity_weight=bad)
    with pytest.raises(ValueError):
        requirement_mass({"a": "minor"}, 100, params=params)
