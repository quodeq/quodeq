"""Tunable scoring parameters for the Q² formula.

The Q² constants in ``constants.py`` remain the canonical defaults; this
module wraps them in an immutable, validated, serializable object so the
formula can run with user overrides without any global mutation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from quodeq.core.scoring.constants import (
    BASE_K,
    CEIL_SCALE,
    GRADE_THRESHOLDS,
    LIFT_COMPRESS,
    SEVERITY_GRADE_FLOOR,
    SEVERITY_WEIGHT,
    Grade,
    MAX_SCORE,
)
from quodeq.core.types.severity import SEVERITY_ORDER

# Canonical grade labels: positions are fixed, only the numeric boundaries move.
GRADE_LABELS: tuple[str, ...] = (Grade.EXEMPLARY, Grade.GOOD, Grade.ADEQUATE, Grade.POOR)

# Mirrors data/config/dimensions.json (pinned by a sync test). Defaults are
# equal (1.0) so the overall score is a plain mean; users can retune per
# dimension in Settings > Grade formula.
_DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "security": 1.0,
    "reliability": 1.0,
    "maintainability": 1.0,
    "performance": 1.0,
    "usability": 1.0,
    "flexibility": 1.0,
    "clean-architecture": 1.0,
    "domain-driven-design": 1.0,
    "accessibility": 1.0,
    "ai-integration-security": 1.0,
}

# Slider ranges: validation enforces them and the editor reads them (ranges_to_dict).
_RANGES: dict[str, tuple[float, float]] = {
    "base_k": (0.01, 1.0),
    "lift_compress": (1.0, 4.0),
    "ceil_scale": (0.0, 2.0),
    "floor_minor": (0.0, 10.0),
    "floor_major": (0.0, 10.0),
}
# Critical needs headroom past its 7.5 default; the editor draws this range on a log slider.
_SEVERITY_WEIGHT_RANGE = (0.05, 25.0)
_DIMENSION_WEIGHT_RANGE = (0.1, 3.0)


@dataclass(frozen=True, slots=True)
class ScoringParams:
    """One full set of Q² formula parameters.

    Mappings are defensively copied and read-only; instances are not hashable.
    """

    severity_weight: Mapping[str, float]
    base_k: float
    lift_compress: float
    ceil_scale: float
    floor_minor: float
    floor_major: float
    grade_thresholds: tuple[tuple[float, str], ...]
    dimension_weights_enabled: bool = True
    dimension_weights: Mapping[str, float] = field(
        default_factory=lambda: dict(_DEFAULT_DIMENSION_WEIGHTS),
    )

    def __post_init__(self) -> None:
        # Defensive copy + read-only wrap: dataclasses.replace() must never
        # alias a mutable mapping with another instance (DEFAULT_PARAMS is a
        # process-wide singleton).
        object.__setattr__(self, "severity_weight", MappingProxyType(dict(self.severity_weight)))
        object.__setattr__(self, "dimension_weights", MappingProxyType(dict(self.dimension_weights)))


DEFAULT_PARAMS = ScoringParams(
    severity_weight=dict(SEVERITY_WEIGHT),
    base_k=BASE_K,
    lift_compress=LIFT_COMPRESS,
    ceil_scale=CEIL_SCALE,
    floor_minor=SEVERITY_GRADE_FLOOR["minor"],
    floor_major=SEVERITY_GRADE_FLOOR["major"],
    grade_thresholds=tuple((float(t), label) for t, label in GRADE_THRESHOLDS),
)


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


def ranges_to_dict() -> dict[str, list[float]]:
    """The bounds validate_params enforces, in the API's camelCase.

    The editor's sliders read these, so they never offer a value the server refuses.
    """
    return {
        "severityWeight": list(_SEVERITY_WEIGHT_RANGE),
        **{_camel(name): list(bounds) for name, bounds in _RANGES.items()},
        "dimensionWeight": list(_DIMENSION_WEIGHT_RANGE),
    }


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


def params_fingerprint(params: ScoringParams) -> str:
    """Deterministic serialization of the grade-formula params (sorted maps)."""
    return json.dumps({
        "severity_weight": dict(sorted(params.severity_weight.items())),
        "base_k": params.base_k,
        "lift_compress": params.lift_compress,
        "ceil_scale": params.ceil_scale,
        "floor_minor": params.floor_minor,
        "floor_major": params.floor_major,
        "grade_thresholds": [list(t) for t in params.grade_thresholds],
        "dimension_weights_enabled": params.dimension_weights_enabled,
        "dimension_weights": dict(sorted(params.dimension_weights.items())),
    }, sort_keys=True)


def grades_stamp(params: ScoringParams) -> str:
    """Short hash of *params*: which formula a run's stored grade tables embody."""
    return hashlib.sha256(params_fingerprint(params).encode("utf-8")).hexdigest()[:16]


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


_COERCION_ERRORS = (TypeError, ValueError, KeyError, AttributeError)


def params_error(data: object) -> str | None:
    """Return ``"Malformed params: <key>"`` naming the first known key whose
    value :func:`params_from_dict` cannot coerce, ``"Malformed params"`` when
    *data* is not a mapping at all, else ``None``.

    Names only our own key (from the defaults' key set), never the coercion
    failure text, so the message is safe to return to an HTTP client.
    """
    if not isinstance(data, Mapping):
        return "Malformed params"
    for key in params_to_dict(DEFAULT_PARAMS):
        if key not in data:
            continue
        try:
            params_from_dict({key: data[key]})
        except _COERCION_ERRORS:
            return f"Malformed params: {key}"
    return None


def validate_params(params: ScoringParams) -> list[str]:
    """Return a list of human-readable validation errors (empty = valid)."""
    errors: list[str] = []
    for name, (lo, hi) in _RANGES.items():
        value = getattr(params, name)
        if not (lo <= value <= hi):
            errors.append(f"{name} must be between {lo} and {hi}, got {value}")
    if params.floor_minor < params.floor_major:
        errors.append("floor_minor must be >= floor_major")
    for sev in SEVERITY_ORDER:
        w = params.severity_weight.get(sev)
        if w is None or not (_SEVERITY_WEIGHT_RANGE[0] <= w <= _SEVERITY_WEIGHT_RANGE[1]):
            errors.append(
                f"severity_weight[{sev}] must be between "
                f"{_SEVERITY_WEIGHT_RANGE[0]} and {_SEVERITY_WEIGHT_RANGE[1]}, got {w}"
            )
    weights = params.severity_weight
    try:
        climbs = weights["minor"] < weights["major"] < weights["critical"]
    except (KeyError, TypeError):
        climbs = False
    if not climbs:
        errors.append("severity weights must be strictly increasing: minor < major < critical")
    labels = tuple(label for _, label in params.grade_thresholds)
    if labels != GRADE_LABELS:
        errors.append(f"grade threshold labels must be {GRADE_LABELS}, got {labels}")
    values = [t for t, _ in params.grade_thresholds]
    if any(b >= a for a, b in zip(values, values[1:])):
        errors.append(f"grade thresholds must be strictly decreasing, got {values}")
    if any(not (0.0 < t < MAX_SCORE) for t in values):
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
