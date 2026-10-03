"""explain_principle exposes the stage values principle_score_and_grade folds into one number."""
from __future__ import annotations

import math

from quodeq.core.scoring.explain import explain_principle
from quodeq.core.scoring.internals import principle_score_and_grade
from quodeq.core.scoring.params import DEFAULT_PARAMS

_VT = {"critical": 0, "major": 1, "minor": 3}
_CT = {"minor": 4}


def test_explain_final_equals_the_scorer() -> None:
    final, grade = principle_score_and_grade(_VT, _CT, params=DEFAULT_PARAMS)
    out = explain_principle(_VT, _CT, params=DEFAULT_PARAMS)
    assert (out["final"], out["grade"]) == (final, grade)


def _weighted() -> float:
    weights = DEFAULT_PARAMS.severity_weight
    return weights["major"] + 3 * weights["minor"]


def test_explain_tallies_and_base() -> None:
    out = explain_principle(_VT, _CT, params=DEFAULT_PARAMS)
    wv = _weighted()
    assert out["types"] == {"critical": 0, "major": 1, "minor": 3}
    assert out["complianceTypes"] == 4
    assert math.isclose(out["weightedViolations"], wv)
    assert math.isclose(out["base"], 10 / (1 + DEFAULT_PARAMS.base_k * wv))


def test_explain_lift_ceiling_floor_and_final() -> None:
    out = explain_principle(_VT, _CT, params=DEFAULT_PARAMS)
    wv = _weighted()
    assert math.isclose(out["lift"], (4 / (4 + wv)) ** DEFAULT_PARAMS.lift_compress)
    assert math.isclose(out["raw"], out["base"] + (10 - out["base"]) * out["lift"])
    assert math.isclose(out["ceiling"], 10 - math.log2(1 + wv) * DEFAULT_PARAMS.ceil_scale)
    assert out["floor"] == DEFAULT_PARAMS.floor_major
    assert out["final"] == round(min(out["ceiling"], max(out["floor"], out["raw"])), 1)


def test_explain_clean_principle() -> None:
    out = explain_principle({}, {"minor": 2}, params=DEFAULT_PARAMS)
    assert (out["weightedViolations"], out["base"], out["lift"], out["final"]) == (0.0, 10.0, 0.0, 10.0)
