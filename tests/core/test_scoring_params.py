"""Tests for the ScoringParams model, validation, and serialization."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    ScoringParams,
    dimension_weighted_average,
    params_from_dict,
    params_to_dict,
    validate_params,
)


def test_defaults_match_q2_constants():
    assert DEFAULT_PARAMS.severity_weight == {"critical": 4.0, "major": 1.5, "minor": 0.25}
    assert DEFAULT_PARAMS.base_k == 0.12
    assert DEFAULT_PARAMS.lift_compress == 1.8
    assert DEFAULT_PARAMS.ceil_scale == 0.5
    assert DEFAULT_PARAMS.floor_minor == 8.0
    assert DEFAULT_PARAMS.floor_major == 5.0
    assert DEFAULT_PARAMS.grade_thresholds == (
        (9.0, "Exemplary"), (7.0, "Good"), (5.0, "Adequate"), (3.0, "Poor"),
    )
    assert DEFAULT_PARAMS.dimension_weights_enabled is True


def test_default_dimension_weights_stay_in_sync_with_dimensions_json():
    data_file = (
        Path(__file__).resolve().parents[2]
        / "src" / "quodeq" / "data" / "config" / "dimensions.json"
    )
    declared = {
        d["id"]: d["weight"] for d in json.loads(data_file.read_text())["applies"]
    }
    assert dict(DEFAULT_PARAMS.dimension_weights) == declared


def test_round_trip_dict_serialization():
    d = params_to_dict(DEFAULT_PARAMS)
    assert d["baseK"] == 0.12
    assert d["gradeThresholds"][0] == [9.0, "Exemplary"]
    restored = params_from_dict(d)
    assert restored == DEFAULT_PARAMS


def test_params_from_partial_dict_falls_back_to_defaults():
    restored = params_from_dict({"baseK": 0.3})
    assert restored.base_k == 0.3
    assert restored.lift_compress == DEFAULT_PARAMS.lift_compress


def test_validate_accepts_defaults():
    assert validate_params(DEFAULT_PARAMS) == []


@pytest.mark.parametrize("field,value,fragment", [
    ("base_k", 0.0, "base_k"),
    ("base_k", 1.5, "base_k"),
    ("lift_compress", 0.5, "lift_compress"),
    ("ceil_scale", -0.1, "ceil_scale"),
    ("floor_minor", 11.0, "floor_minor"),
])
def test_validate_rejects_out_of_range(field, value, fragment):
    import dataclasses
    bad = dataclasses.replace(DEFAULT_PARAMS, **{field: value})
    errors = validate_params(bad)
    assert any(fragment in e for e in errors)


def test_validate_rejects_floor_minor_below_floor_major():
    import dataclasses
    bad = dataclasses.replace(DEFAULT_PARAMS, floor_minor=2.0, floor_major=3.0)
    assert any("floor_minor" in e for e in validate_params(bad))


def test_validate_rejects_non_decreasing_thresholds():
    import dataclasses
    bad = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=(
        (9.0, "Exemplary"), (9.5, "Good"), (5.0, "Adequate"), (3.0, "Poor"),
    ))
    assert any("decreasing" in e for e in validate_params(bad))


def test_validate_rejects_renamed_threshold_labels():
    import dataclasses
    bad = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=(
        (9.0, "Amazing"), (7.0, "Good"), (5.0, "Adequate"), (3.0, "Poor"),
    ))
    assert any("label" in e for e in validate_params(bad))


def test_validate_rejects_nonpositive_severity_weight():
    import dataclasses
    bad = dataclasses.replace(
        DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 0.0, "minor": 0.25},
    )
    assert any("severity_weight" in e for e in validate_params(bad))


def test_dimension_weighted_average_disabled_is_plain_mean():
    import dataclasses
    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=False)
    pairs = [("security", 8.0), ("performance", 6.0)]
    assert dimension_weighted_average(pairs, params) == 7.0


def test_dimension_weighted_average_enabled_weights_by_dimension():
    import dataclasses
    # Default weights are all 1.0; set explicit per-dimension weights to
    # exercise the weighting math.
    params = dataclasses.replace(
        DEFAULT_PARAMS,
        dimension_weights_enabled=True,
        dimension_weights={"security": 1.2, "performance": 0.8},
    )
    # security weight 1.2, performance 0.8 → (8*1.2 + 6*0.8) / 2.0 = 7.2
    pairs = [("security", 8.0), ("performance", 6.0)]
    assert dimension_weighted_average(pairs, params) == 7.2


def test_dimension_weighted_average_unknown_dimension_defaults_to_1():
    import dataclasses
    params = dataclasses.replace(
        DEFAULT_PARAMS,
        dimension_weights_enabled=True,
        dimension_weights={"security": 1.2},
    )
    pairs = [("not-a-dim", 8.0), ("security", 6.0)]
    # (8*1.0 + 6*1.2) / 2.2 = 15.2/2.2 = 6.909... → 6.9
    assert dimension_weighted_average(pairs, params) == 6.9


def test_dimension_weighted_average_empty_returns_none():
    assert dimension_weighted_average([], DEFAULT_PARAMS) is None


def test_mappings_are_read_only():
    import pytest as _pytest
    with _pytest.raises(TypeError):
        DEFAULT_PARAMS.dimension_weights["security"] = 9.9  # type: ignore[index]
    with _pytest.raises(TypeError):
        DEFAULT_PARAMS.severity_weight["critical"] = 9.9  # type: ignore[index]


def test_replace_does_not_alias_default_mappings():
    import dataclasses
    copy = dataclasses.replace(DEFAULT_PARAMS, base_k=0.3)
    assert copy.dimension_weights is not DEFAULT_PARAMS.dimension_weights
    assert copy.severity_weight is not DEFAULT_PARAMS.severity_weight
