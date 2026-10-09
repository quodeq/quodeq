"""The spec's constants are the defaults, and weights must climb the ladder."""
from __future__ import annotations

import dataclasses

from quodeq.core.scoring.constants import BASE_K, LIFT_COMPRESS, SEVERITY_GRADE_FLOOR, SEVERITY_WEIGHT
from quodeq.core.scoring.params import DEFAULT_PARAMS, validate_params


def test_defaults_match_the_spec():
    assert SEVERITY_WEIGHT == {"critical": 4.0, "major": 2.0, "minor": 0.25}
    assert BASE_K == 0.08
    assert LIFT_COMPRESS == 2.2
    assert SEVERITY_GRADE_FLOOR == {"critical": 0.0, "major": 3.0, "minor": 5.0}
    assert (DEFAULT_PARAMS.floor_major, DEFAULT_PARAMS.floor_minor) == (3.0, 5.0)
    assert validate_params(DEFAULT_PARAMS) == []


def test_non_increasing_weights_are_rejected():
    params = dataclasses.replace(DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 4.0, "minor": 0.25})
    errors = validate_params(params)
    assert any("strictly increasing" in e for e in errors)


def test_a_none_weight_is_an_error_not_a_crash():
    params = dataclasses.replace(DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": None, "minor": 0.25})
    errors = validate_params(params)
    assert any("strictly increasing" in e for e in errors)
