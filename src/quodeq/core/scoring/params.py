"""Tunable scoring parameters for the Q² formula.

The Q² constants in ``_constants.py`` remain the canonical defaults; this
module wraps them in an immutable, validated, serializable object so the
formula can run with user overrides without any global mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from quodeq.core.scoring._constants import (
    _BASE_K,
    _CEIL_SCALE,
    _GRADE_THRESHOLDS,
    _LIFT_COMPRESS,
    _SEVERITY_GRADE_FLOOR,
    _SEVERITY_WEIGHT,
)

# Canonical grade labels: positions are fixed, only the numeric boundaries move.
GRADE_LABELS: tuple[str, ...] = ("Exemplary", "Good", "Adequate", "Poor")

# Mirrors data/config/dimensions.json (pinned by a sync test).
_DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "security": 1.2,
    "reliability": 1.0,
    "maintainability": 1.0,
    "performance": 0.8,
    "usability": 0.6,
    "flexibility": 0.6,
    "clean-architecture": 1.0,
    "domain-driven-design": 1.0,
}

# Slider ranges shared by validation and (conceptually) the UI.
_RANGES: dict[str, tuple[float, float]] = {
    "base_k": (0.01, 1.0),
    "lift_compress": (1.0, 4.0),
    "ceil_scale": (0.0, 2.0),
    "floor_minor": (0.0, 10.0),
    "floor_major": (0.0, 10.0),
}
_SEVERITY_WEIGHT_RANGE = (0.05, 10.0)
_DIMENSION_WEIGHT_RANGE = (0.1, 3.0)


@dataclass(frozen=True, slots=True)
class ScoringParams:
    """One full set of Q² formula parameters."""
    severity_weight: Mapping[str, float]
    base_k: float
    lift_compress: float
    ceil_scale: float
    floor_minor: float
    floor_major: float
    grade_thresholds: tuple[tuple[float, str], ...]
    dimension_weights_enabled: bool = False
    dimension_weights: Mapping[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_DIMENSION_WEIGHTS),
    )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScoringParams):
            return NotImplemented
        return params_to_dict(self) == params_to_dict(other)


DEFAULT_PARAMS = ScoringParams(
    severity_weight=MappingProxyType(dict(_SEVERITY_WEIGHT)),
    base_k=_BASE_K,
    lift_compress=_LIFT_COMPRESS,
    ceil_scale=_CEIL_SCALE,
    floor_minor=_SEVERITY_GRADE_FLOOR["minor"],
    floor_major=_SEVERITY_GRADE_FLOOR["major"],
    grade_thresholds=tuple((float(t), label) for t, label in _GRADE_THRESHOLDS),
)


def params_to_dict(params: ScoringParams) -> dict[str, Any]:
    """Serialize to the camelCase shape used by the API and the JSON file."""
    return {
        "severityWeight": dict(params.severity_weight),
        "baseK": params.base_k,
        "liftCompress": params.lift_compress,
        "ceilScale": params.ceil_scale,
        "floorMinor": params.floor_minor,
        "floorMajor": params.floor_major,
        "gradeThresholds": [[t, label] for t, label in params.grade_thresholds],
        "dimensionWeightsEnabled": params.dimension_weights_enabled,
        "dimensionWeights": dict(params.dimension_weights),
    }


def params_from_dict(data: Mapping[str, Any]) -> ScoringParams:
    """Build params from a (possibly partial) camelCase dict; missing keys default."""
    d = params_to_dict(DEFAULT_PARAMS)
    d.update({k: v for k, v in data.items() if k in d})
    return ScoringParams(
        severity_weight={k: float(v) for k, v in d["severityWeight"].items()},
        base_k=float(d["baseK"]),
        lift_compress=float(d["liftCompress"]),
        ceil_scale=float(d["ceilScale"]),
        floor_minor=float(d["floorMinor"]),
        floor_major=float(d["floorMajor"]),
        grade_thresholds=tuple((float(t), str(label)) for t, label in d["gradeThresholds"]),
        dimension_weights_enabled=bool(d["dimensionWeightsEnabled"]),
        dimension_weights={k: float(v) for k, v in d["dimensionWeights"].items()},
    )


def validate_params(params: ScoringParams) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    for name, (lo, hi) in _RANGES.items():
        value = getattr(params, name)
        if not (lo <= value <= hi):
            errors.append(f"{name} must be between {lo} and {hi}, got {value}")
    if params.floor_minor < params.floor_major:
        errors.append("floor_minor must be >= floor_major")
    for sev in ("critical", "major", "minor"):
        w = params.severity_weight.get(sev)
        if w is None or not (_SEVERITY_WEIGHT_RANGE[0] <= w <= _SEVERITY_WEIGHT_RANGE[1]):
            errors.append(
                f"severity_weight[{sev}] must be between "
                f"{_SEVERITY_WEIGHT_RANGE[0]} and {_SEVERITY_WEIGHT_RANGE[1]}, got {w}"
            )
    labels = tuple(label for _, label in params.grade_thresholds)
    if labels != GRADE_LABELS:
        errors.append(f"grade threshold labels must be {GRADE_LABELS}, got {labels}")
    values = [t for t, _ in params.grade_thresholds]
    if any(b >= a for a, b in zip(values, values[1:])):
        errors.append(f"grade thresholds must be strictly decreasing, got {values}")
    if any(not (0.0 < t < 10.0) for t in values):
        errors.append(f"grade thresholds must be within (0, 10), got {values}")
    for dim, w in params.dimension_weights.items():
        if not (_DIMENSION_WEIGHT_RANGE[0] <= w <= _DIMENSION_WEIGHT_RANGE[1]):
            errors.append(
                f"dimension_weights[{dim}] must be between "
                f"{_DIMENSION_WEIGHT_RANGE[0]} and {_DIMENSION_WEIGHT_RANGE[1]}, got {w}"
            )
    return errors


def dimension_weighted_average(
    pairs: Iterable[tuple[str | None, float]],
    params: ScoringParams,
) -> float | None:
    """Average dimension scores, weighting by dimension id when enabled.

    *pairs* is (dimension_id, score). Unknown dimensions weigh 1.0.
    Returns None when there is nothing to average.
    """
    items = list(pairs)
    if not items:
        return None
    if not params.dimension_weights_enabled:
        return round(sum(score for _, score in items) / len(items), 1)
    total_weight = 0.0
    total_value = 0.0
    for dim, score in items:
        w = params.dimension_weights.get(dim or "", 1.0)
        total_weight += w
        total_value += score * w
    return round(total_value / total_weight, 1)
