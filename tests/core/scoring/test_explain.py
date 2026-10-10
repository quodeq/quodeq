"""explain_principle exposes every stage value principle_score_and_grade folds into one number."""
from __future__ import annotations

import math

from quodeq.core.scoring.explain import explain_principle
from quodeq.core.scoring.internals import principle_score_and_grade
from quodeq.core.scoring.mass import principle_mass, requirement_rows, spread
from quodeq.core.scoring.params import DEFAULT_PARAMS

_FILES = 1000
_V = [{"req": "R-1", "file": "a", "severity": "major"}] + [{"req": "R-2", "file": f"b{i}", "severity": "minor"} for i in range(3)]
_C = [{"req": "R-3", "file": f"c{i}"} for i in range(4)]
_MASS = principle_mass(requirement_rows(_V, _C), _FILES, params=DEFAULT_PARAMS)


def test_explain_final_equals_the_scorer() -> None:
    final, grade = principle_score_and_grade(_MASS, params=DEFAULT_PARAMS)
    out = explain_principle(_MASS, params=DEFAULT_PARAMS)
    assert (out["final"], out["grade"]) == (final, grade)


def test_explain_masses_and_rows() -> None:
    out = explain_principle(_MASS, params=DEFAULT_PARAMS)
    assert (out["violationRules"], out["complianceRules"]) == (2, 1)
    assert math.isclose(out["violationMass"], _MASS.violation_mass)
    assert math.isclose(out["complianceMass"], spread(4, _FILES))
    assert math.isclose(out["observation"], _MASS.observation)
    r1 = next(r for r in out["requirements"] if r["req"] == "R-1")
    assert "class" not in r1
    assert r1["filesAtLeastMajor"] == 1 and r1["filesAtLeastCritical"] == 0 and math.isclose(r1["spreadMajor"], spread(1, _FILES))
    assert out["compliance"] == [{"req": "R-3", "filesOk": 4, "spread": spread(4, _FILES)}]


def test_explain_stages() -> None:
    out = explain_principle(_MASS, params=DEFAULT_PARAMS)
    wv = _MASS.violation_mass
    assert math.isclose(out["base"], 10 / (1 + DEFAULT_PARAMS.base_k * wv))
    assert math.isclose(out["ceiling"], 10 - math.log2(1 + wv) * DEFAULT_PARAMS.ceil_scale)
    assert out["floor"] == DEFAULT_PARAMS.floor_major  # worst severity is the major finding
    assert out["final"] == round(min(out["ceiling"], max(out["floor"], out["raw"])), 1)


def test_explain_clean_principle() -> None:
    mass = principle_mass(requirement_rows([], [{"req": "R-1", "file": "a"}]), _FILES, params=DEFAULT_PARAMS)
    out = explain_principle(mass, params=DEFAULT_PARAMS)
    assert (out["violationMass"], out["base"], out["lift"], out["final"]) == (0.0, 10.0, 0.0, 10.0)
