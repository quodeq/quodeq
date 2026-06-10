# Grade Formula Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Settings screen where users tune the Q² grading formula with sliders/switches, see a live before/after preview computed server-side from real findings, and Apply the custom params as the installation-wide grading policy (all runs rescore).

**Architecture:** A frozen `ScoringParams` dataclass is threaded explicitly through the six pure scoring functions and every read-time aggregation point (no global mutation). Custom params persist at `~/.quodeq/grade_formula.json` behind a small service; a read-only preview endpoint recomputes one run in memory; Apply rewrites every run's SQL grade tables (cheap — grades are projections of `events.jsonl`). The UI adds a tabbed `grade-formula` page with a debounced server preview, and all client-side grade-label logic unifies onto thresholds served by the API.

**Tech Stack:** Python 3.12 / Flask / SQLite / pytest (run via `uv run pytest`); React + Vite UI (no router — custom nav stack), `node --test` for plain JS unit tests.

**Spec:** `docs/superpowers/specs/2026-06-10-grade-formula-editor-design.md`

**Working conventions (apply to every task):**
- Branch: `feat/grade-formula-editor` (already created). Never push to develop. Never add co-author lines to commits.
- `export PATH="$HOME/.local/bin:$PATH"` before any `uv` command.
- All backend test commands run from the repo root `/Users/victor/GitHub/quodeq`. UI commands run from `src/quodeq/ui`.
- No em-dashes in any user-facing UI string.
- `docs/` is gitignored: commit doc files with `git add -f`.

---

## File Map

**Create (backend):**
- `src/quodeq/core/scoring/params.py` — `ScoringParams`, `DEFAULT_PARAMS`, validation, dict (de)serialization, `dimension_weighted_average`
- `src/quodeq/services/grade_formula.py` — load/save/reset persistence, apply-to-all-runs pipeline, preview
- `src/quodeq/api/_grade_formula_routes.py` — GET/PUT/DELETE `/api/grade-formula`, POST `/api/grade-formula/preview`
- `tests/engine/test_scoring_params.py`, `tests/services/test_grade_formula.py`, `tests/api/test_grade_formula_api.py`

**Modify (backend):**
- `src/quodeq/core/scoring/_tallies.py` (`_weighted_sum` takes weights)
- `src/quodeq/core/scoring/internals.py` (5 formula functions take params)
- `src/quodeq/core/scoring/_principle.py`, `overall.py`, `engine.py` (thread params)
- `src/quodeq/core/scoring/numerical.py` (delete dormant `configure_penalties` global)
- `src/quodeq/services/scoring/projector_scoring.py`, `src/quodeq/services/rescore.py`
- `src/quodeq/data/fs/report_parser/_summary.py`, `src/quodeq/services/accumulated.py`
- `src/quodeq/data/sqlite/state_store.py` (`read_run_score_from_dim_scores`)
- `src/quodeq/data/projection/grade_projector.py` (pure compute + preview split)
- `src/quodeq/services/dashboard.py` (shared-cache clear fn)
- `src/quodeq/engine/scoring_pipeline.py`, `src/quodeq/services/evaluation_mixin.py` (CLI entry loads saved params)
- `src/quodeq/api/routes_registry.py`

**Create (UI):**
- `src/quodeq/ui/src/utils/gradeThresholds.js` (+ `gradeThresholds.test.js`)
- `src/quodeq/ui/src/features/grade-formula/useGradeFormula.js`
- `src/quodeq/ui/src/features/grade-formula/GradeFormulaPage.jsx`
- `src/quodeq/ui/src/features/grade-formula/ParamSlider.jsx`
- `src/quodeq/ui/src/features/grade-formula/PreviewStrip.jsx`
- `src/quodeq/ui/src/features/grade-formula/CurvePlot.jsx`
- `src/quodeq/ui/src/features/grade-formula/GradeBoundaryBar.jsx`
- `src/quodeq/ui/src/features/grade-formula/tabs.jsx` (the four tab bodies)

**Modify (UI):**
- `src/quodeq/ui/src/api/index.js` (4 client functions)
- `src/quodeq/ui/src/utils/formatters.js` (dynamic thresholds)
- `src/quodeq/ui/src/features/dashboard/components/DimensionGaugeCard.jsx` (use shared label fn)
- `src/quodeq/ui/src/features/map/viz/core/galaxyCore.js` (`scoreRGB` dynamic)
- `src/quodeq/ui/src/App.jsx` (route + settings wiring + boot fetch)
- `src/quodeq/ui/src/features/settings/components/SettingsPage.jsx` (entry section)

**Delete (UI):** `src/quodeq/ui/src/features/dashboard/components/dimensionGradeLabel.js` + its test.

**Docs:** update `docs/adr/0001-dimension-level-weighting-not-yet-applied.md`, `src/quodeq/core/scoring/README.md`, `docs/ui-map.md`.

---

### Task 1: `ScoringParams` model

**Files:**
- Create: `src/quodeq/core/scoring/params.py`
- Test: `tests/engine/test_scoring_params.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    assert DEFAULT_PARAMS.floor_minor == 5.0
    assert DEFAULT_PARAMS.floor_major == 3.0
    assert DEFAULT_PARAMS.grade_thresholds == (
        (9.0, "Exemplary"), (7.0, "Good"), (5.0, "Adequate"), (3.0, "Poor"),
    )
    assert DEFAULT_PARAMS.dimension_weights_enabled is False


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
    pairs = [("security", 8.0), ("performance", 6.0)]
    assert dimension_weighted_average(pairs, DEFAULT_PARAMS) == 7.0


def test_dimension_weighted_average_enabled_weights_by_dimension():
    import dataclasses
    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=True)
    # security weight 1.2, performance 0.8 → (8*1.2 + 6*0.8) / 2.0 = 7.2
    pairs = [("security", 8.0), ("performance", 6.0)]
    assert dimension_weighted_average(pairs, params) == 7.2


def test_dimension_weighted_average_unknown_dimension_defaults_to_1():
    import dataclasses
    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=True)
    pairs = [("not-a-dim", 8.0), ("security", 6.0)]
    # (8*1.0 + 6*1.2) / 2.2 = 15.2/2.2 = 6.909... → 6.9
    assert dimension_weighted_average(pairs, params) == 6.9


def test_dimension_weighted_average_empty_returns_none():
    assert dimension_weighted_average([], DEFAULT_PARAMS) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `export PATH="$HOME/.local/bin:$PATH" && uv run pytest tests/engine/test_scoring_params.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'quodeq.core.scoring.params'`

- [ ] **Step 3: Implement `params.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_scoring_params.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/core/scoring/params.py tests/engine/test_scoring_params.py
git commit -m "feat(scoring): ScoringParams model with validation and serialization"
```

---

### Task 2: Thread params through `_tallies` and `internals`

**Files:**
- Modify: `src/quodeq/core/scoring/_tallies.py:52-57`
- Modify: `src/quodeq/core/scoring/internals.py:42-101`
- Test: `tests/engine/test_scoring_internals.py` (append new tests; existing must stay green)

- [ ] **Step 1: Append failing tests to `tests/engine/test_scoring_internals.py`**

```python
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
```

(If the test file does not already import `pytest`, add `import pytest` at the top.)

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/engine/test_scoring_internals.py -v -k "custom"`
Expected: FAIL with `TypeError: ... got an unexpected keyword argument 'params'`

- [ ] **Step 3: Modify `_tallies.py`**

Change `_weighted_sum` (keep all other functions untouched):

```python
from typing import Mapping

from quodeq.core.scoring._constants import _SEVERITY_WEIGHT


def _weighted_sum(
    type_counts: dict[str, int],
    severity_weight: Mapping[str, float] | None = None,
) -> float:
    """Sum type counts weighted by severity."""
    weights = severity_weight if severity_weight is not None else _SEVERITY_WEIGHT
    fallback = weights.get("minor", 0.25)
    return sum(
        count * weights.get(sev, fallback)
        for sev, count in type_counts.items()
    )
```

- [ ] **Step 4: Modify `internals.py`**

Add the import and thread params through the five functions (leave `compliance_dampening`, `drop_grade`, `weight_as_multiplier` untouched — legacy graded mode is out of scope):

```python
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams


def violation_base(
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Compute the base score from violations alone (ignoring compliance).

    Uses a hyperbolic curve: ``base = 10 / (1 + K * weighted_violations)``
    Returns a value in [0, 10].
    """
    wv = _weighted_sum(violation_type_counts, params.severity_weight)
    if wv == 0:
        return 10.0
    return 10.0 / (1.0 + params.base_k * wv)


def compliance_lift(
    compliance_type_counts: dict[str, int],
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Compute the lift factor from compliance evidence.

    Returns a value in [0, 1] representing the fraction of the gap filled.
    """
    wv = _weighted_sum(violation_type_counts, params.severity_weight)
    cc = sum(compliance_type_counts.get(sev, 0) for sev in compliance_type_counts)
    if cc == 0 or wv == 0:
        return 0.0
    raw_lift = cc / (cc + wv)
    return raw_lift ** params.lift_compress


def violation_ceiling(
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Compute the maximum achievable score given the violation weight.

    ``ceiling = 10 - log2(1 + wv) * CEIL_SCALE``
    """
    wv = _weighted_sum(violation_type_counts, params.severity_weight)
    if wv == 0:
        return 10.0
    return 10.0 - math.log2(1.0 + wv) * params.ceil_scale


def severity_grade_floor(
    violation_type_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> float:
    """Return the minimum score based on the worst violation severity present."""
    if violation_type_counts.get("critical", 0) > 0:
        return 0.0
    if violation_type_counts.get("major", 0) > 0:
        return params.floor_major
    if violation_type_counts.get("minor", 0) > 0:
        return params.floor_minor
    return 10.0


def score_to_grade_label(
    score: float, *, params: ScoringParams = DEFAULT_PARAMS,
) -> str:
    """Convert a 0-10 numerical score to a descriptive grade label."""
    for threshold, label in params.grade_thresholds:
        if score >= threshold:
            return label
    return "Critical"
```

- [ ] **Step 5: Run the full scoring test files**

Run: `uv run pytest tests/engine/test_scoring_internals.py tests/engine/test_scoring.py tests/engine/test_scoring_graded.py tests/engine/test_scoring_params.py -v`
Expected: all PASS (defaults are unchanged, so pinned assertions stay green)

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/core/scoring/_tallies.py src/quodeq/core/scoring/internals.py tests/engine/test_scoring_internals.py
git commit -m "feat(scoring): thread ScoringParams through formula internals"
```

---

### Task 3: Thread params through `_principle`, `overall`, `engine`

**Files:**
- Modify: `src/quodeq/core/scoring/_principle.py:68-138`
- Modify: `src/quodeq/core/scoring/overall.py:44-77`
- Modify: `src/quodeq/core/scoring/engine.py:11-48`
- Test: `tests/engine/test_scoring.py` (append)

- [ ] **Step 1: Append failing test to `tests/engine/test_scoring.py`**

```python
# --- params threading through run_scoring ------------------------------------
import dataclasses

from quodeq.core.scoring.params import DEFAULT_PARAMS


def test_run_scoring_with_strict_params_lowers_scores():
    """The same evidence scores lower when severity weights are raised."""
    from quodeq.core.scoring.engine import run_scoring

    evidence = {
        "repository": "r", "discipline": "d", "date": "2026-06-10",
        "source_file_count": 100, "files_read": 100,
        "principles": {
            "p1": {
                "display_name": "P1", "weight": "1",
                "metrics": {
                    "compliance_percentage": 50.0, "confidence_level": "high",
                    "is_balanced": True, "total_instances": 20,
                },
                "violations": [
                    {"severity": "major", "reason": f"r{i}"} for i in range(5)
                ],
                "compliance": [
                    {"severity": "minor", "reason": f"c{i}"} for i in range(10)
                ],
            },
        },
    }
    default_result = run_scoring(evidence, "numerical")
    strict = dataclasses.replace(
        DEFAULT_PARAMS,
        severity_weight={"critical": 4.0, "major": 5.0, "minor": 0.25},
    )
    strict_result = run_scoring(evidence, "numerical", params=strict)
    assert strict_result.overall.weighted_score < default_result.overall.weighted_score
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/engine/test_scoring.py -v -k strict_params`
Expected: FAIL with `TypeError: run_scoring() got an unexpected keyword argument 'params'`

- [ ] **Step 3: Modify `_principle.py`**

Add to imports: `from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams`. Change `_score_numerical`, `_score_graded`, and `_score_all_principles`:

```python
def _score_numerical(
    ctx: _PrincipleContext, params: ScoringParams = DEFAULT_PARAMS,
) -> PrincipleScore:
    """Score a single principle in numerical mode."""
    kwargs = _base_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs, base_score=0,
            deductions=build_deductions({}, scale_multiplier=ctx.scale_mult),
            final_score=0.0, grade="Insufficient",
        )
    base = violation_base(ctx.vt_counts, params=params)
    lift = compliance_lift(ctx.ct_counts, ctx.vt_counts, params=params)
    raw = base + (_BASE_SCORE - base) * lift
    final_pts = round(max(severity_grade_floor(ctx.vt_counts, params=params),
                          min(violation_ceiling(ctx.vt_counts, params=params), raw)), 1)
    return PrincipleScore(
        **kwargs, base_score=round(base, 1),
        deductions=build_deductions(ctx.vt_counts, scale_multiplier=ctx.scale_mult),
        dampening_multiplier=lift, final_score=final_pts,
        grade=score_to_grade_label(final_pts, params=params),
    )


def _score_graded(
    ctx: _PrincipleContext, params: ScoringParams = DEFAULT_PARAMS,  # noqa: ARG001
) -> PrincipleScore:
    """Score a single principle in non-numerical (graded) mode.

    Accepts params only for scorer-signature symmetry with
    ``_score_numerical``; the legacy graded ladder is not user-tunable.
    """
    kwargs = _base_kwargs(ctx)
    if ctx.conf_level == "low":
        return PrincipleScore(
            **kwargs, base_grade="Insufficient", severity_drops=0,
            grade="Insufficient",
        )
    drops = count_grade_drops(ctx.vt_counts, scale_multiplier=ctx.scale_mult)
    return PrincipleScore(
        **kwargs, base_grade="Exemplary", severity_drops=drops,
        dampening_multiplier=ctx.dampening,
        grade=drop_grade("Exemplary", int(drops * ctx.dampening)),
    )


def _score_all_principles(
    raw_principles: dict, mode: str, scale_mult: int, files_read: int,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, PrincipleScore]:
    """Score every principle and return the per-principle dict."""
    scorer = _score_numerical if mode == MODE_NUMERICAL else _score_graded
    return {
        key: scorer(_build_context(key, pdata, scale_mult, files_read), params)
        for key, pdata in raw_principles.items()
    }
```

- [ ] **Step 4: Modify `overall.py`**

Add import `from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams` and thread:

```python
def build_overall_result(
    mode: str, total_weight: int, total_value: float,
    params: ScoringParams = DEFAULT_PARAMS,
) -> OverallScore:
    """Build the overall result from aggregated weights."""
    if mode == MODE_NUMERICAL:
        mean_score = round(total_value / total_weight, 1)
        return OverallScore(
            weighted_score=mean_score,
            grade=score_to_grade_label(mean_score, params=params),
            total_weight=total_weight,
        )
    mean_index = total_value / total_weight
    ladder_pos = min(len(GRADE_LADDER) - 1, round(mean_index))
    return OverallScore(weighted_grade=GRADE_LADDER[ladder_pos], total_weight=total_weight)


def weighted_overall(
    principles_scores: dict[str, PrincipleScore], mode: str,
    params: ScoringParams = DEFAULT_PARAMS,
) -> OverallScore:
    """Compute a weighted overall score or grade from per-principle results."""
    tw, tv, total, insuff = accumulate_weights(principles_scores, mode)

    if tw == 0:
        if mode == MODE_NUMERICAL:
            return OverallScore(weighted_score=0.0, grade="Insufficient")
        return OverallScore(weighted_grade="Insufficient")

    result = build_overall_result(mode, tw, tv, params)
    # (insufficient-majority block unchanged)
```

- [ ] **Step 5: Modify `engine.py`**

```python
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams


def run_scoring(
    evidence: dict, mode: str, params: ScoringParams = DEFAULT_PARAMS,
) -> ScoringResult:
    """Compute per-principle scores and return the full result."""
    source_file_count = evidence.get("source_file_count", 0)
    files_read = evidence.get("files_read", 0)
    scale_mult = scale_multiplier(source_file_count)

    per_principle = _score_all_principles(
        evidence.get("principles", {}), mode, scale_mult, files_read, params,
    )
    return ScoringResult(
        repository=evidence.get("repository", ""),
        discipline=evidence.get("discipline", ""),
        date=evidence.get("date", ""),
        mode=mode,
        principles=per_principle,
        overall=weighted_overall(per_principle, mode, params),
        scale=ScaleInfo(
            tier=SCALE_TIER_NAMES.get(scale_mult, "Small"),
            multiplier=scale_mult,
            files_read=files_read,
        ),
    )


def score_evidence(
    evidence: Evidence, mode: str = "numerical",
    params: ScoringParams = DEFAULT_PARAMS,
) -> ScoringResult:
    """Score Evidence using the scoring engine."""
    return run_scoring(evidence.to_evidence_dict(), mode=mode, params=params)
```

- [ ] **Step 6: Run the engine test suite**

Run: `uv run pytest tests/engine/ -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/core/scoring/_principle.py src/quodeq/core/scoring/overall.py src/quodeq/core/scoring/engine.py tests/engine/test_scoring.py
git commit -m "feat(scoring): thread ScoringParams through principle, overall, engine"
```

---

### Task 4: Delete dormant `configure_penalties` global

**Files:**
- Modify: `src/quodeq/core/scoring/numerical.py:14-56,77-100`
- Modify: `src/quodeq/core/scoring/internals.py` (re-export list, if it exports them — check)

- [ ] **Step 1: Confirm there are no callers**

Run: `grep -rn "configure_penalties\|reset_penalty_caches\|_penalty_config" src/ tests/ --include="*.py"`
Expected: matches only inside `src/quodeq/core/scoring/numerical.py`. If a test or caller appears, STOP and reassess before deleting.

- [ ] **Step 2: Delete the global config block**

In `numerical.py`, delete the `_PenaltyConfig` dataclass, the `_penalty_config` module global, `configure_penalties()`, and `reset_penalty_caches()` (lines 21-56). Simplify `build_deductions`'s resolution block to:

```python
def build_deductions(
    violation_type_counts: dict[str, int],
    scale_multiplier: int = 1,
    *,
    critical_penalty: float | None = None,
    major_penalty: float | None = None,
    minor_penalty: float | None = None,
) -> Deductions:
    # docstring unchanged
    crit_pen = critical_penalty if critical_penalty is not None else _DEFAULT_CRITICAL_PENALTY
    maj_pen = major_penalty if major_penalty is not None else _DEFAULT_MAJOR_PENALTY
    min_pen = minor_penalty if minor_penalty is not None else _DEFAULT_MINOR_PENALTY
    # rest unchanged (remove the `config` parameter entirely)
```

Also update the comment at lines 13-14 (`# Override via configure_penalties()...`) to `# Per-type deduction constants for numerical mode.`

- [ ] **Step 3: Run full backend suite to catch import fallout**

Run: `uv run pytest tests/ -x -q`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/core/scoring/numerical.py
git commit -m "refactor(scoring): remove dormant configure_penalties global"
```

---

### Task 5: Thread params through service read paths and run-level aggregation

**Files:**
- Modify: `src/quodeq/services/scoring/projector_scoring.py` (3 functions)
- Modify: `src/quodeq/services/rescore.py` (4 functions)
- Modify: `src/quodeq/data/fs/report_parser/_summary.py:12-46`
- Modify: `src/quodeq/services/accumulated.py:26-30` (`numeric_average`) and its `score_to_grade_label` call in the response builder
- Modify: `src/quodeq/data/sqlite/state_store.py:193-201`
- Modify: `src/quodeq/services/scoring/__init__.py` (`_build_summary_from_dim_dicts` label call, ~line 157)
- Test: `tests/services/scoring/test_projector_scoring.py` (append)

- [ ] **Step 1: Append failing tests to `tests/services/scoring/test_projector_scoring.py`**

```python
# --- params threading ---------------------------------------------------------
import dataclasses

from quodeq.core.scoring.params import DEFAULT_PARAMS


def test_compute_dimension_score_with_custom_thresholds_changes_grade():
    params = dataclasses.replace(DEFAULT_PARAMS, grade_thresholds=(
        (9.9, "Exemplary"), (9.0, "Good"), (8.0, "Adequate"), (7.0, "Poor"),
    ))
    from quodeq.services.scoring.projector_scoring import compute_dimension_score
    grades = [{"score": 8.5, "grade": "Good"}]
    result = compute_dimension_score(
        dimension="security", principle_grades=grades, params=params,
    )
    assert result["grade"] == "Adequate"


def test_compute_run_score_applies_dimension_weights_when_enabled():
    params = dataclasses.replace(DEFAULT_PARAMS, dimension_weights_enabled=True)
    from quodeq.services.scoring.projector_scoring import compute_run_score
    dims = [
        {"dimension": "security", "score": 8.0},
        {"dimension": "performance", "score": 6.0},
    ]
    result = compute_run_score(dims, params=params)
    # security 1.2, performance 0.8 → (8*1.2 + 6*0.8) / 2.0 = 7.2
    assert result["score"] == 7.2


def test_compute_run_score_plain_mean_when_disabled():
    from quodeq.services.scoring.projector_scoring import compute_run_score
    dims = [
        {"dimension": "security", "score": 8.0},
        {"dimension": "performance", "score": 6.0},
    ]
    assert compute_run_score(dims)["score"] == 7.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/scoring/test_projector_scoring.py -v -k "custom_thresholds or dimension_weights or plain_mean"`
Expected: FAIL with `TypeError` (unexpected keyword `params`)

- [ ] **Step 3: Modify `projector_scoring.py`**

Add import `from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average`. Thread params:

```python
def compute_principle_grade(
    *,
    principle_id: str,
    findings: list[Finding],
    compliance: list[Finding],
    dismissed_count: int = 0,
    source_file_count: int = 0,
    scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    # ... unchanged until the scoring block, then:
    base = violation_base(vt_counts, params=params)
    lift = compliance_lift(ct_counts, vt_counts, params=params)
    ceil = violation_ceiling(vt_counts, params=params)
    floor = severity_grade_floor(vt_counts, params=params)

    raw = base + (10.0 - base) * lift
    final = max(floor, min(ceil, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)
    # return unchanged


def compute_dimension_score(
    *,
    dimension: str,
    principle_grades: list[dict[str, Any]],
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Average non-Insufficient principle scores into a dimension-level score."""
    scored = [p for p in principle_grades if p.get("score") is not None]
    if not scored:
        return {"dimension": dimension, "score": None, "grade": "Insufficient"}
    avg = round(sum(p["score"] for p in scored) / len(scored), 1)
    return {
        "dimension": dimension, "score": avg,
        "grade": score_to_grade_label(avg, params=params),
    }


def compute_run_score(
    dimension_scores: list[dict[str, Any]],
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Average non-null dimension scores into a run-level score.

    Applies per-dimension weights when params enable them.
    """
    pairs = [
        (d.get("dimension"), d["score"])
        for d in dimension_scores if d.get("score") is not None
    ]
    avg = dimension_weighted_average(pairs, params)
    if avg is None:
        return {"score": None, "grade": None}
    return {"score": avg, "grade": score_to_grade_label(avg, params=params)}
```

- [ ] **Step 4: Modify `rescore.py`**

Add import `from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams`. Thread `params` through `_score_principle`, `_score_all_principles`, `_rescore_dimension`, and `rescore_dimensions`:

```python
def _score_principle(
    violations: list[Finding], compliance: list[Finding],
    *, source_file_count: int = 0, scale_multiplier: int = 1,
    params: ScoringParams = DEFAULT_PARAMS,
) -> tuple[float | None, str]:
    # ... confidence gate unchanged, then:
    base = violation_base(vt_counts, params=params)
    lift = compliance_lift(ct_counts, vt_counts, params=params)
    ceil = violation_ceiling(vt_counts, params=params)
    floor = severity_grade_floor(vt_counts, params=params)

    raw = base + (10.0 - base) * lift
    final = max(floor, min(ceil, raw))
    final = round(final, 1)
    grade = score_to_grade_label(final, params=params)
    return final, grade
```

`_score_all_principles` gains `params: ScoringParams = DEFAULT_PARAMS` and passes it to `_score_principle(...)`. `_rescore_dimension` gains `params: ScoringParams = DEFAULT_PARAMS`, passes it to `_score_all_principles(...)` and to `weighted_overall(principle_scores, MODE_NUMERICAL, params)`. In THIS task `rescore_dimensions` also takes a plain default (Task 7 flips it to load the saved file):

```python
def rescore_dimensions(
    dimensions: list[DimensionResult],
    dismissed_keys: set[tuple],
    deleted_keys: set[tuple] | None = None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    rescored = [
        _rescore_dimension(dim, dismissed_keys, deleted_keys, params=params)
        for dim in dimensions
    ]
    summary = summarize_dimensions(rescored, params=params)
    return {
        "dimensions": [to_camel_dict(d) for d in rescored],
        "summary": to_camel_dict(summary),
    }
```

- [ ] **Step 5: Modify `_summary.py`**

```python
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average


def summarize_dimensions(
    dimensions: list[DimensionResult],
    params: ScoringParams = DEFAULT_PARAMS,
) -> DimensionSummary:
    # docstring unchanged
    overall_grades = [d.overall_grade for d in dimensions if d.overall_grade]
    score_pairs = [
        (d.dimension, score)
        for d, score in (
            (d, parse_numeric_score(d.overall_score)) for d in dimensions
        )
        if score is not None
    ]
    numeric_average = dimension_weighted_average(score_pairs, params)

    grade_counts: dict[str, int] = {}
    for grade in overall_grades:
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

    if numeric_average is not None:
        overall_grade = score_to_grade_label(numeric_average, params=params)
    else:
        overall_grade = most_frequent_grade(overall_grades)
    # return unchanged
```

- [ ] **Step 6: Modify `accumulated.py`**

`numeric_average` becomes params-aware (callers updated in Task 7):

```python
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams, dimension_weighted_average


def numeric_average(
    dimensions: list[DimensionResult],
    params: ScoringParams = DEFAULT_PARAMS,
) -> float | None:
    """Compute the average numeric score from a list of DimensionResult objects."""
    pairs = [
        (d.dimension, score)
        for d, score in ((d, parse_numeric_score(d.overall_score)) for d in dimensions if d.overall_score)
        if score is not None
    ]
    return dimension_weighted_average(pairs, params)
```

Find the `score_to_grade_label(` call(s) inside this module (`grep -n "score_to_grade_label" src/quodeq/services/accumulated.py`) and pass `params=params` through the enclosing function(s), giving each a `params: ScoringParams = DEFAULT_PARAMS` keyword.

- [ ] **Step 7: Modify `state_store.read_run_score_from_dim_scores`**

```python
    def read_run_score_from_dim_scores(self, params=None) -> dict:
        """Compute run-level score as the mean of non-null dimension scores."""
        from quodeq.services.scoring.projector_scoring import compute_run_score  # noqa: PLC0415
        from quodeq.core.scoring.params import DEFAULT_PARAMS  # noqa: PLC0415
        rows = self.read_dimension_scores()
        return compute_run_score(rows, params=params if params is not None else DEFAULT_PARAMS)
```

(This removes the duplicated mean+label logic; `compute_run_score` is the single implementation. The data→services import is a lazy call-time import, same precedent as `grade_projector.py`.)

- [ ] **Step 8: Modify `services/scoring/__init__.py` summary label call**

`grep -n "score_to_grade_label" src/quodeq/services/scoring/__init__.py` (~line 157 in `_build_summary_from_dim_dicts`): give that function a `params: ScoringParams = DEFAULT_PARAMS` keyword and pass `params=params` to the label call; import `DEFAULT_PARAMS, ScoringParams` from `quodeq.core.scoring.params`. Find callers of `_build_summary_from_dim_dicts` and `read_run_score_from_dim_scores` inside the module and thread the keyword (default keeps them working).

- [ ] **Step 9: Run service + parity suites**

Run: `uv run pytest tests/services/ -q`
Expected: all PASS (parity tests confirm projector and rescore still agree under defaults)

- [ ] **Step 10: Commit**

```bash
git add src/quodeq/services/scoring/projector_scoring.py src/quodeq/services/rescore.py src/quodeq/data/fs/report_parser/_summary.py src/quodeq/services/accumulated.py src/quodeq/data/sqlite/state_store.py src/quodeq/services/scoring/__init__.py tests/services/scoring/test_projector_scoring.py
git commit -m "feat(scoring): params-aware service read paths and weighted run aggregation"
```

---

### Task 6: `grade_formula` persistence service

**Files:**
- Create: `src/quodeq/services/grade_formula.py`
- Test: `tests/services/test_grade_formula.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for grade-formula params persistence."""
from __future__ import annotations

import dataclasses
import json

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services import grade_formula


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setattr(grade_formula, "grade_formula_path", lambda: path)
    return path


def test_load_returns_defaults_when_file_absent(formula_path):
    assert grade_formula.load_params() == DEFAULT_PARAMS
    assert grade_formula.is_custom() is False


def test_save_then_load_round_trips(formula_path):
    custom = dataclasses.replace(DEFAULT_PARAMS, base_k=0.3)
    grade_formula.save_params(custom)
    assert formula_path.is_file()
    assert grade_formula.load_params() == custom
    assert grade_formula.is_custom() is True


def test_load_falls_back_to_defaults_on_corrupt_file(formula_path):
    formula_path.write_text("{not json")
    assert grade_formula.load_params() == DEFAULT_PARAMS


def test_reset_removes_file(formula_path):
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    grade_formula.reset_params()
    assert not formula_path.exists()
    assert grade_formula.is_custom() is False


def test_save_rejects_invalid_params(formula_path):
    bad = dataclasses.replace(DEFAULT_PARAMS, base_k=99.0)
    with pytest.raises(ValueError):
        grade_formula.save_params(bad)
    assert not formula_path.exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/test_grade_formula.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`

- [ ] **Step 3: Implement `services/grade_formula.py`** (apply pipeline and preview are added in Tasks 8-9; keep this file persistence-only for now)

```python
"""Persistence for user-tuned grade formula parameters.

The file at ``~/.quodeq/grade_formula.json`` holds the camelCase dict shape
from ``params_to_dict``. Absent file means Q² defaults. A corrupt file logs
a warning and falls back to defaults rather than breaking every score read.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    ScoringParams,
    params_from_dict,
    params_to_dict,
    validate_params,
)

_logger = logging.getLogger(__name__)


def grade_formula_path() -> Path:
    """Location of the custom-params file (function so tests can monkeypatch)."""
    return Path.home() / ".quodeq" / "grade_formula.json"


def load_params() -> ScoringParams:
    """Return saved custom params, or Q² defaults when absent or unreadable."""
    path = grade_formula_path()
    if not path.is_file():
        return DEFAULT_PARAMS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        params = params_from_dict(data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        _logger.warning("Unreadable %s (%s); using Q2 default formula.", path, exc)
        return DEFAULT_PARAMS
    if validate_params(params):
        _logger.warning("Invalid params in %s; using Q2 default formula.", path)
        return DEFAULT_PARAMS
    return params


def save_params(params: ScoringParams) -> None:
    """Validate and persist custom params. Raises ValueError when invalid."""
    errors = validate_params(params)
    if errors:
        raise ValueError("; ".join(errors))
    path = grade_formula_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params_to_dict(params), indent=2), encoding="utf-8")


def reset_params() -> None:
    """Remove the custom-params file (back to Q² defaults)."""
    grade_formula_path().unlink(missing_ok=True)


def is_custom() -> bool:
    """True when a custom-params file is in effect."""
    return grade_formula_path().is_file()
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/services/test_grade_formula.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/services/grade_formula.py tests/services/test_grade_formula.py
git commit -m "feat(grade-formula): params persistence service"
```

---

### Task 7: Wire saved params into every default path

**Files:**
- Modify: `src/quodeq/services/rescore.py` (`rescore_dimensions` default)
- Modify: `src/quodeq/data/projection/grade_projector.py` (`recompute_grades` signature)
- Modify: `src/quodeq/engine/scoring_pipeline.py:28`
- Modify: `src/quodeq/services/evaluation_mixin.py:610`
- Modify: `src/quodeq/services/scoring/__init__.py` and `src/quodeq/services/accumulated.py` (resolve loaded params once per request and pass down)
- Test: `tests/services/test_grade_formula.py` (append)

- [ ] **Step 1: Append failing test**

```python
def test_rescore_dimensions_uses_saved_params(formula_path, monkeypatch):
    """rescore_dimensions with no explicit params picks up the saved file."""
    import dataclasses
    from quodeq.services.rescore import rescore_dimensions

    seen = {}
    def fake_load():
        seen["called"] = True
        return dataclasses.replace(DEFAULT_PARAMS, base_k=0.3)
    monkeypatch.setattr(grade_formula, "load_params", fake_load)

    rescore_dimensions([], set())
    assert seen.get("called") is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/test_grade_formula.py -v -k uses_saved`
Expected: FAIL (`load_params` never called — `rescore_dimensions` still defaults to `DEFAULT_PARAMS`)

- [ ] **Step 3: Flip the boundary defaults to `None` + lazy `load_params()`**

In `rescore.py`:

```python
def rescore_dimensions(
    dimensions: list[DimensionResult],
    dismissed_keys: set[tuple],
    deleted_keys: set[tuple] | None = None,
    params: ScoringParams | None = None,
) -> dict[str, Any]:
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    ...
```

In `grade_projector.py` (full param threading; the compute/write split comes in Task 8):

```python
def recompute_grades(run_dir: Path, params: ScoringParams | None = None) -> None:
    """Full recompute of dimension_scores + principle_grades from findings."""
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    ...
    # pass params=params to every compute_principle_grade(...) and
    # compute_dimension_score(...) call in the function body
```

(Add `from quodeq.core.scoring.params import ScoringParams` to its imports.)

In `engine/scoring_pipeline.py` line 28 and `services/evaluation_mixin.py` line 610, load once and pass:

```python
from quodeq.services.grade_formula import load_params
...
scores = score_evidence(evidence, mode=mode, params=load_params())
```

In `services/scoring/__init__.py`: at the top of `get_project_scores` and `get_scores_raw`, resolve `params = load_params()` once and pass it down to `_build_summary_from_dim_dicts(...)`, `read_run_score_from_dim_scores(params)`, `rescore_dimensions(..., params=params)` and `compute_accumulated(...)`/`numeric_average(...)` call chains touched in Task 5 (follow each keyword you added there; `grep -n "params" src/quodeq/services/scoring/__init__.py` after editing to confirm every Task-5 keyword has a caller passing the loaded value).

In `services/accumulated.py`: give `compute_accumulated` a `params: ScoringParams | None = None` keyword, resolve via `grade_formula.load_params()` when `None`, and pass it to `numeric_average(...)` and the `score_to_grade_label(...)` call sites threaded in Task 5.

- [ ] **Step 4: Run the affected suites**

Run: `uv run pytest tests/services/ tests/engine/ -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/services/rescore.py src/quodeq/data/projection/grade_projector.py src/quodeq/engine/scoring_pipeline.py src/quodeq/services/evaluation_mixin.py src/quodeq/services/scoring/__init__.py src/quodeq/services/accumulated.py tests/services/test_grade_formula.py
git commit -m "feat(grade-formula): saved params drive all scoring entry points"
```

---

### Task 8: Pure run-grade computation + preview + apply pipeline

**Files:**
- Modify: `src/quodeq/data/projection/grade_projector.py` (extract pure compute)
- Modify: `src/quodeq/services/grade_formula.py` (add preview + apply)
- Modify: `src/quodeq/services/dashboard.py` (cache clear)
- Test: `tests/services/test_grade_formula.py` (append)

- [ ] **Step 1: Append failing tests**

These tests need a run fixture with an `evaluation.db`. Reuse the repo's existing helpers if present: `grep -rn "record_finding\|judgment" tests/services/ tests/data/ | head` and copy the established fixture style for inserting findings. A minimal self-contained fixture:

```python
import dataclasses
from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.data.projection.grade_projector import compute_run_grades, recompute_grades
from quodeq.core.scoring.params import DEFAULT_PARAMS


def _make_run(tmp_path: Path) -> Path:
    """Create a run dir with findings and baked default grade tables."""
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text("")  # marker; findings inserted directly
    store = SQLiteStateStore(run_dir)
    # Insert findings via the store's record_finding(Judgment) API; mirror the
    # field names used in tests/data tests for Judgment construction.
    for i in range(6):
        store.record_finding(Judgment(
            practice_id="p1", dimension="security", requirement=f"req{i}",
            verdict="violation", severity="major", file=f"f{i}.py", line=1,
            title=f"t{i}", reason=f"r{i}",
        ))
    for i in range(8):
        store.record_finding(Judgment(
            practice_id="p1", dimension="security", requirement=f"c{i}",
            verdict="compliance", severity="minor", file=f"g{i}.py", line=1,
            title=f"ct{i}", reason=f"cr{i}",
        ))
    recompute_grades(run_dir, params=DEFAULT_PARAMS)
    return run_dir


def test_compute_run_grades_is_pure(tmp_path):
    run_dir = _make_run(tmp_path)
    store = SQLiteStateStore(run_dir)
    before_rows = store.read_dimension_scores()

    strict = dataclasses.replace(
        DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 6.0, "minor": 0.25},
    )
    principle_rows, dim_rows = compute_run_grades(run_dir, strict)

    assert dim_rows  # something was computed
    # and nothing was written:
    assert store.read_dimension_scores() == before_rows


def test_preview_equals_apply(tmp_path):
    """THE invariant: preview numbers == numbers after writing with same params."""
    run_dir = _make_run(tmp_path)
    strict = dataclasses.replace(
        DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 6.0, "minor": 0.25},
    )
    _, preview_dims = compute_run_grades(run_dir, strict)
    recompute_grades(run_dir, params=strict)
    applied = SQLiteStateStore(run_dir).read_dimension_scores()
    applied_by_dim = {r["dimension"]: (r["score"], r["grade"]) for r in applied}
    for d in preview_dims:
        assert applied_by_dim[d["dimension"]] == (d["score"], d["grade"])


def test_apply_to_all_runs_rescores_and_skips_legacy(tmp_path, formula_path, monkeypatch):
    from quodeq.services import grade_formula
    project_dir = tmp_path / "proj-uuid"
    project_dir.mkdir()
    run_dir = project_dir / "run1"
    # _make_run builds under tmp_path; rebuild here under the project dir
    import shutil
    shutil.move(str(_make_run(tmp_path)), str(run_dir))
    legacy = project_dir / "run0"
    legacy.mkdir()  # no events.jsonl → must be skipped

    strict = dataclasses.replace(
        DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 6.0, "minor": 0.25},
    )
    grade_formula.save_params(strict)
    count = grade_formula.apply_to_all_runs(tmp_path)
    assert count == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/services/test_grade_formula.py -v -k "pure or preview_equals or apply_to_all"`
Expected: FAIL with `ImportError: cannot import name 'compute_run_grades'`

If `Judgment(...)` construction fails, check `src/quodeq/core/events/models.py` for the exact required fields and adjust the fixture; do not change production code for the fixture.

- [ ] **Step 3: Refactor `grade_projector.py` into compute + write**

```python
def compute_run_grades(
    run_dir: Path, params: ScoringParams,
) -> tuple[list[tuple[str, dict]], list[dict]]:
    """Compute (principle_rows, dimension_rows) from findings. Pure: no writes.

    principle_rows: [(dimension, principle_grade_dict), ...]
    dimension_rows: [{"dimension":..., "score":..., "grade":...}, ...]
    """
    source_file_count = _read_source_file_count(run_dir)

    with open_evaluation_db(run_dir) as conn:
        dismissed_raw = conn.execute(_SELECT_DISMISSED_COUNTS).fetchall()
        dismissed_counts = {(r[0], r[1]): r[2] for r in dismissed_raw}
        conn.row_factory = _dict_row
        rows = conn.execute(_SELECT_NON_DISMISSED).fetchall()

    findings = [row_to_finding(r) for r in rows]

    violations_by: dict[tuple[str, str], list[Finding]] = {}
    compliance_by: dict[tuple[str, str], list[Finding]] = {}
    for f in findings:
        key = (f.dimension or "", f.practice_id or "")
        bucket = violations_by if f.verdict == "violation" else compliance_by
        bucket.setdefault(key, []).append(f)

    principle_grades_by_dim: dict[str, list[dict]] = {}
    principle_rows: list[tuple[str, dict]] = []
    for dim, principle_id in sorted(set(violations_by) | set(compliance_by)):
        grade = compute_principle_grade(
            principle_id=principle_id,
            findings=violations_by.get((dim, principle_id), []),
            compliance=compliance_by.get((dim, principle_id), []),
            dismissed_count=dismissed_counts.get((dim, principle_id), 0),
            source_file_count=source_file_count,
            params=params,
        )
        principle_grades_by_dim.setdefault(dim, []).append(grade)
        principle_rows.append((dim, grade))

    dimension_rows = [
        compute_dimension_score(dimension=dim, principle_grades=p_grades, params=params)
        for dim, p_grades in principle_grades_by_dim.items()
    ]
    return principle_rows, dimension_rows


def recompute_grades(run_dir: Path, params: ScoringParams | None = None) -> None:
    """Full recompute of dimension_scores + principle_grades from findings."""
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    principle_rows, dimension_rows = compute_run_grades(run_dir, params)

    store = SQLiteStateStore(run_dir)
    store.clear_grades()
    for dim, p_grade in principle_rows:
        store.record_principle_grade(
            dimension=dim,
            principle_id=p_grade["principle_id"],
            score=p_grade["score"],
            grade=p_grade["grade"],
            finding_count=p_grade["finding_count"],
            dismissed_count=p_grade["dismissed_count"],
        )
    for d_score in dimension_rows:
        store.record_dimension_score(
            dimension=d_score["dimension"],
            score=d_score["score"],
            grade=d_score["grade"],
        )
```

- [ ] **Step 4: Add cache clear to `dashboard.py`** (below `create_dimension_cache`, ~line 90)

```python
def clear_shared_dimension_cache() -> None:
    """Drop all cached run-dimension data (e.g. after a formula change)."""
    with _SHARED_RUN_DIM_LOCK:
        _SHARED_RUN_DIM_CACHE.clear()
```

- [ ] **Step 5: Add apply + preview to `services/grade_formula.py`**

```python
# append to the existing imports
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams  # already there
# (keep persistence functions; append below them)


def apply_to_all_runs(reports_root: Path) -> int:
    """Rescore every run that has an events.jsonl with the currently saved params.

    Legacy runs without an event log cannot be rescored and are skipped.
    Returns the number of runs rescored.
    """
    from quodeq.data.projection.grade_projector import recompute_grades  # noqa: PLC0415
    from quodeq.services.dashboard import clear_shared_dimension_cache  # noqa: PLC0415

    params = load_params()
    count = 0
    if reports_root.is_dir():
        for project_dir in sorted(p for p in reports_root.iterdir() if p.is_dir()):
            for run_dir in sorted(r for r in project_dir.iterdir() if r.is_dir()):
                if not (run_dir / "events.jsonl").is_file():
                    continue
                try:
                    recompute_grades(run_dir, params=params)
                    count += 1
                except Exception:  # noqa: BLE001 — one bad run must not block the rest
                    _logger.warning("Rescore failed for %s; skipping.", run_dir, exc_info=True)
    clear_shared_dimension_cache()
    return count


def preview_scores(
    reports_root: Path, project: str, params: ScoringParams,
) -> dict | None:
    """Recompute the project's latest event-log run in memory with *params*.

    Read-only: never writes evaluation.db. Returns None when the project has
    no run with an events.jsonl.
    """
    from quodeq.data.projection.grade_projector import compute_run_grades  # noqa: PLC0415
    from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: PLC0415
    from quodeq.services.scoring.projector_scoring import compute_run_score  # noqa: PLC0415

    project_dir = reports_root / project
    if not project_dir.is_dir():
        return None
    run_dirs = sorted(
        (r for r in project_dir.iterdir()
         if r.is_dir() and (r / "events.jsonl").is_file()),
        key=lambda p: p.name, reverse=True,
    )
    if not run_dirs:
        return None
    run_dir = run_dirs[0]

    saved = load_params()
    store = SQLiteStateStore(run_dir)
    before_dims = store.read_dimension_scores()
    before_overall = compute_run_score(before_dims, params=saved)

    _, after_dims = compute_run_grades(run_dir, params)
    after_overall = compute_run_score(after_dims, params=params)

    def _payload(dims: list[dict], overall: dict) -> dict:
        return {
            "overall": overall,
            "dimensions": [
                {"dimension": d["dimension"], "score": d["score"], "grade": d["grade"]}
                for d in sorted(dims, key=lambda x: x["dimension"] or "")
            ],
        }

    return {
        "project": project,
        "runId": run_dir.name,
        "before": _payload(before_dims, before_overall),
        "after": _payload(after_dims, after_overall),
    }
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/services/test_grade_formula.py tests/data/ -q`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/quodeq/data/projection/grade_projector.py src/quodeq/services/grade_formula.py src/quodeq/services/dashboard.py tests/services/test_grade_formula.py
git commit -m "feat(grade-formula): pure run-grade compute, preview, apply-to-all pipeline"
```

---

### Task 9: API routes

**Files:**
- Create: `src/quodeq/api/_grade_formula_routes.py`
- Modify: `src/quodeq/api/routes_registry.py`
- Test: `tests/api/test_grade_formula_api.py`

- [ ] **Step 1: Write the failing tests**

Look at `tests/api/test_action_api.py` first for how the suite builds a test app (`create_app(...)` fixture conventions, auth headers if any) and reuse that fixture style. The assertions to implement:

```python
"""Contract tests for /api/grade-formula endpoints."""
from __future__ import annotations

import dataclasses

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS, params_to_dict
from quodeq.services import grade_formula


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setattr(grade_formula, "grade_formula_path", lambda: path)
    return path


# `client` fixture: copy the Flask test-client setup from tests/api/test_action_api.py.


def test_get_returns_defaults_and_is_custom_false(client, formula_path):
    resp = client.get("/api/grade-formula")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["isCustom"] is False
    assert body["current"] == params_to_dict(DEFAULT_PARAMS)
    assert body["defaults"] == params_to_dict(DEFAULT_PARAMS)


def test_put_saves_and_applies(client, formula_path, monkeypatch):
    applied = {}
    monkeypatch.setattr(
        grade_formula, "apply_to_all_runs", lambda root: applied.setdefault("n", 7) or 7,
    )
    payload = params_to_dict(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.put("/api/grade-formula", json=payload)
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["isCustom"] is True
    assert body["applied"] == 7
    assert grade_formula.load_params().base_k == 0.3


def test_put_rejects_invalid_params_with_400(client, formula_path):
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = 99.0
    resp = client.put("/api/grade-formula", json=payload)
    assert resp.status_code == 400
    assert not formula_path.exists()


def test_delete_resets_to_defaults(client, formula_path, monkeypatch):
    monkeypatch.setattr(grade_formula, "apply_to_all_runs", lambda root: 0)
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    resp = client.delete("/api/grade-formula")
    assert resp.status_code == 200
    assert resp.get_json()["isCustom"] is False
    assert not formula_path.exists()


def test_preview_returns_404_when_no_runs(client, formula_path, monkeypatch):
    monkeypatch.setattr(grade_formula, "preview_scores", lambda root, project, params: None)
    resp = client.post(
        "/api/grade-formula/preview",
        json={"project": "nope", "params": params_to_dict(DEFAULT_PARAMS)},
    )
    assert resp.status_code == 404


def test_preview_returns_before_after(client, formula_path, monkeypatch):
    fake = {
        "project": "p", "runId": "r1",
        "before": {"overall": {"score": 7.4, "grade": "Good"}, "dimensions": []},
        "after": {"overall": {"score": 6.8, "grade": "Adequate"}, "dimensions": []},
    }
    monkeypatch.setattr(grade_formula, "preview_scores", lambda root, project, params: fake)
    resp = client.post(
        "/api/grade-formula/preview",
        json={"project": "p", "params": params_to_dict(DEFAULT_PARAMS)},
    )
    assert resp.status_code == 200
    assert resp.get_json() == fake


def test_preview_rejects_invalid_params(client, formula_path):
    payload = params_to_dict(DEFAULT_PARAMS)
    payload["baseK"] = 99.0
    resp = client.post("/api/grade-formula/preview", json={"project": "p", "params": payload})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/api/test_grade_formula_api.py -v`
Expected: FAIL with 404s (routes not registered)

- [ ] **Step 3: Implement `_grade_formula_routes.py`**

```python
"""Grade formula endpoints.

GET    /api/grade-formula          -- current + defaults + isCustom
PUT    /api/grade-formula          -- validate, save, rescore all runs
DELETE /api/grade-formula          -- reset to Q2 defaults, rescore all runs
POST   /api/grade-formula/preview  -- read-only before/after for one project
"""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from flask import Flask, Response, jsonify, request

from quodeq.api.helpers import error_response
from quodeq.api.routes_common import reports_dir
from quodeq.core.scoring.params import (
    DEFAULT_PARAMS,
    params_from_dict,
    params_to_dict,
    validate_params,
)
from quodeq.services import grade_formula


def _parse_params(data: dict) -> tuple:
    """Returns (params, None) or (None, (response, status)) on validation error."""
    try:
        params = params_from_dict(data or {})
    except (TypeError, ValueError, KeyError) as exc:
        body, status = error_response(
            f"Malformed params: {exc}", HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
        return None, (jsonify(body), status)
    errors = validate_params(params)
    if errors:
        body, status = error_response(
            "; ".join(errors), HTTPStatus.BAD_REQUEST, "INVALID_INPUT",
        )
        return None, (jsonify(body), status)
    return params, None


def _state_payload(applied: int | None = None) -> dict:
    payload = {
        "current": params_to_dict(grade_formula.load_params()),
        "defaults": params_to_dict(DEFAULT_PARAMS),
        "isCustom": grade_formula.is_custom(),
    }
    if applied is not None:
        payload["applied"] = applied
    return payload


def register_grade_formula_routes(app: Flask) -> None:
    """Register grade formula endpoints."""

    @app.get("/api/grade-formula")
    def get_grade_formula() -> Response:
        return jsonify(_state_payload())

    @app.put("/api/grade-formula")
    def put_grade_formula() -> Response | tuple[Response, int]:
        params, err = _parse_params(request.get_json(silent=True))
        if err:
            return err
        grade_formula.save_params(params)
        applied = grade_formula.apply_to_all_runs(Path(reports_dir()))
        return jsonify(_state_payload(applied=applied))

    @app.delete("/api/grade-formula")
    def delete_grade_formula() -> Response:
        grade_formula.reset_params()
        applied = grade_formula.apply_to_all_runs(Path(reports_dir()))
        return jsonify(_state_payload(applied=applied))

    @app.post("/api/grade-formula/preview")
    def preview_grade_formula() -> Response | tuple[Response, int]:
        payload = request.get_json(silent=True) or {}
        project = payload.get("project") or ""
        params, err = _parse_params(payload.get("params") or {})
        if err:
            return err
        result = grade_formula.preview_scores(Path(reports_dir()), project, params)
        if result is None:
            body, status = error_response(
                "No evaluation with an event log found for this project",
                HTTPStatus.NOT_FOUND, "NOT_FOUND",
            )
            return jsonify(body), status
        return jsonify(result)
```

- [ ] **Step 4: Register in `routes_registry.py`**

Add the import and call (next to `register_scores_routes(app)`):

```python
from quodeq.api._grade_formula_routes import register_grade_formula_routes
...
    register_scores_routes(app)
    register_grade_formula_routes(app)
```

- [ ] **Step 5: Run the API suite**

Run: `uv run pytest tests/api/test_grade_formula_api.py tests/api/test_app_factory.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/api/_grade_formula_routes.py src/quodeq/api/routes_registry.py tests/api/test_grade_formula_api.py
git commit -m "feat(api): grade-formula endpoints (get/put/delete/preview)"
```

---

### Task 10: UI api client + dynamic grade thresholds (label unification)

**Files:**
- Modify: `src/quodeq/ui/src/api/index.js`
- Create: `src/quodeq/ui/src/utils/gradeThresholds.js`
- Create: `src/quodeq/ui/src/utils/gradeThresholds.test.js`
- Modify: `src/quodeq/ui/src/utils/formatters.js:41-54,204-212`
- Modify: `src/quodeq/ui/src/features/dashboard/components/DimensionGaugeCard.jsx:9,107`
- Modify: `src/quodeq/ui/src/features/map/viz/core/galaxyCore.js:81-88`
- Delete: `src/quodeq/ui/src/features/dashboard/components/dimensionGradeLabel.js` and `dimensionGradeLabel.test.js`

- [ ] **Step 1: Write the failing util test (`gradeThresholds.test.js`)**

```js
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  getGradeThresholds, setGradeThresholds, resetGradeThresholds, scoreToGradeLabel,
} from './gradeThresholds.js';

beforeEach(() => resetGradeThresholds());

test('defaults match backend Q2 thresholds', () => {
  assert.deepEqual(getGradeThresholds(), [
    [9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor'],
  ]);
});

test('scoreToGradeLabel maps with defaults', () => {
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
  assert.equal(scoreToGradeLabel(7.0), 'Good');
  assert.equal(scoreToGradeLabel(5.1), 'Adequate');
  assert.equal(scoreToGradeLabel(3.0), 'Poor');
  assert.equal(scoreToGradeLabel(2.9), 'Critical');
});

test('scoreToGradeLabel handles strings like "9.1/10" and bad input', () => {
  assert.equal(scoreToGradeLabel('9.1/10'), 'Exemplary');
  assert.equal(scoreToGradeLabel(null), null);
  assert.equal(scoreToGradeLabel('n/a'), null);
});

test('setGradeThresholds changes the mapping', () => {
  setGradeThresholds([[9.5, 'Exemplary'], [8, 'Good'], [6, 'Adequate'], [4, 'Poor']]);
  assert.equal(scoreToGradeLabel(9.2), 'Good');
  assert.equal(scoreToGradeLabel(3.9), 'Critical');
});

test('setGradeThresholds ignores junk', () => {
  setGradeThresholds(undefined);
  setGradeThresholds([]);
  assert.equal(scoreToGradeLabel(9.2), 'Exemplary');
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd src/quodeq/ui && npm run test`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `gradeThresholds.js`**

```js
/**
 * Single client-side source of truth for score → grade-label boundaries.
 * Seeded with the backend Q2 defaults; App.jsx overwrites them at boot from
 * GET /api/grade-formula so every surface agrees with the server formula.
 */
const DEFAULT_THRESHOLDS = [
  [9, 'Exemplary'], [7, 'Good'], [5, 'Adequate'], [3, 'Poor'],
];

let thresholds = DEFAULT_THRESHOLDS;

export function getGradeThresholds() {
  return thresholds;
}

export function setGradeThresholds(next) {
  if (!Array.isArray(next) || next.length === 0) return;
  const clean = next
    .filter((e) => Array.isArray(e) && typeof e[0] === 'number' && typeof e[1] === 'string')
    .map((e) => [e[0], e[1]]);
  if (clean.length === next.length && clean.length > 0) thresholds = clean;
}

export function resetGradeThresholds() {
  thresholds = DEFAULT_THRESHOLDS;
}

/** Numeric or "9.1/10"-style input → label string, or null for bad input. */
export function scoreToGradeLabel(score) {
  if (score === null || score === undefined || score === '') return null;
  const n = typeof score === 'number' ? score : parseFloat(score);
  if (Number.isNaN(n)) return null;
  for (const [threshold, label] of thresholds) {
    if (n >= threshold) return label;
  }
  return 'Critical';
}
```

- [ ] **Step 4: Run util tests**

Run: `cd src/quodeq/ui && npm run test`
Expected: PASS

- [ ] **Step 5: Switch consumers to the shared thresholds**

`formatters.js` — delete the four `SCORE_*` constants (lines 41-44) and rewrite the two threshold-driven functions:

```js
import { getGradeThresholds } from './gradeThresholds.js';

const GRADE_CLASSES = ['grade-top', 'grade-high', 'grade-mid', 'grade-low'];
const TIER_LETTERS = ['A', 'B', 'C', 'D'];

export function scoreColorClass(score) {
  const n = typeof score === 'number' ? score : parseFloat(score);
  if (Number.isNaN(n)) return 'grade-bottom';
  const thresholds = getGradeThresholds();
  for (let i = 0; i < thresholds.length; i += 1) {
    if (n >= thresholds[i][0]) return GRADE_CLASSES[i] ?? 'grade-low';
  }
  return 'grade-bottom';
}

export function scoreTierLabel(score) {
  const n = typeof score === 'number' ? score : parseFloat(score);
  if (Number.isNaN(n)) return null;
  const thresholds = getGradeThresholds();
  for (let i = 0; i < thresholds.length; i += 1) {
    if (n >= thresholds[i][0]) return TIER_LETTERS[i] ?? 'D';
  }
  return 'F';
}
```

(Keep the original guard clauses of each function if they differ — open the file and preserve surrounding behavior, only replacing the hardcoded comparisons.)

`DimensionGaugeCard.jsx` — replace the import on line 9 and the call on line 107:

```js
import { scoreToGradeLabel } from '../../../utils/gradeThresholds.js';
...
const label = hasScore ? scoreToGradeLabel(scoreNum) : null;
const gradeWord = label ? label.toUpperCase() : null;
```

(Note: this intentionally removes the divergent FAIR tier — gauge labels now match the rest of the app and the backend.)

`galaxyCore.js` — make `scoreRGB` threshold-driven:

```js
import { getGradeThresholds } from '../../../../utils/gradeThresholds.js';

const GRADE_COLOR_KEYS = ['gradeTop', 'gradeHigh', 'gradeMid', 'gradeLow'];

export function scoreRGB(score) {
  const tc = getThemeColors();
  const thresholds = getGradeThresholds();
  for (let i = 0; i < thresholds.length; i += 1) {
    if (score >= thresholds[i][0]) return tc[GRADE_COLOR_KEYS[i]] ?? tc.gradeLow;
  }
  return tc.gradeBottom;
}
```

(Verify the relative import depth with `ls`; galaxyCore.js sits at `features/map/viz/core/`, so `utils/` is four levels up.)

Delete `dimensionGradeLabel.js` and `dimensionGradeLabel.test.js`; then `grep -rn "dimensionGradeLabel" src/quodeq/ui/src` must return nothing.

- [ ] **Step 6: Add the API client functions (`api/index.js`)**

```js
// ── Grade formula ───────────────────────────────────────────────────────

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean}>} */
export function getGradeFormula() {
  return request('/grade-formula');
}

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, applied: number}>} */
export function saveGradeFormula(params) {
  return request('/grade-formula', { method: 'PUT', body: JSON.stringify(params) });
}

/** @returns {Promise<{current: Object, defaults: Object, isCustom: boolean, applied: number}>} */
export function resetGradeFormula() {
  return request('/grade-formula', { method: 'DELETE' });
}

/** @returns {Promise<{project: string, runId: string, before: Object, after: Object}>} */
export function previewGradeFormula(projectId, params) {
  return request('/grade-formula/preview', {
    method: 'POST',
    body: JSON.stringify({ project: projectId, params }),
  });
}
```

(Open `src/quodeq/ui/src/api/request.js` first to confirm `request()` prefixes `/api` — `getHealth()` calls `request('/health')` for `/api/health`, so these paths follow the same convention.)

- [ ] **Step 7: Run UI tests + dev build**

Run: `cd src/quodeq/ui && npm run test && npm run build`
Expected: tests PASS, build succeeds (catches any missed `dimensionGradeLabel` import)

- [ ] **Step 8: Commit**

```bash
git add -A src/quodeq/ui/src
git commit -m "feat(ui): served grade thresholds unify all label surfaces; grade-formula api client"
```

---

### Task 11: UI building blocks — slider, preview strip, hook

**Files:**
- Create: `src/quodeq/ui/src/features/grade-formula/ParamSlider.jsx`
- Create: `src/quodeq/ui/src/features/grade-formula/PreviewStrip.jsx`
- Create: `src/quodeq/ui/src/features/grade-formula/useGradeFormula.js`

- [ ] **Step 1: `ParamSlider.jsx`**

```jsx
/**
 * Labeled range slider with numeric readout and a one-line hint.
 * Controlled: value/onChange. No free-text input by design.
 */
export default function ParamSlider({ label, value, min, max, step, hint, disabled, onChange }) {
  return (
    <div className="gf-slider-row">
      <label className="gf-slider-label">
        <span className="settings-label">{label}</span>
        <span className="gf-slider-value">{value}</span>
      </label>
      <input
        type="range"
        className="gf-slider"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label={label}
      />
      {hint ? <span className="settings-description">{hint}</span> : null}
    </div>
  );
}
```

Add the supporting CSS to `src/quodeq/ui/src/styles/base.css` (append, following the `.settings-*` conventions and theme tokens; class prefix `gf-`):

```css
/* ── Grade formula editor ── */
.gf-slider-row { display: flex; flex-direction: column; gap: 2px; margin-bottom: 12px; }
.gf-slider-label { display: flex; justify-content: space-between; align-items: baseline; }
.gf-slider-value { font-family: var(--font-mono, monospace); color: var(--color-accent); }
.gf-slider { width: 100%; accent-color: var(--color-accent); }
.gf-tabs { display: flex; gap: 0; margin-top: 12px; }
.gf-tab { padding: 4px 12px; border: 1px solid var(--color-border); border-bottom: none;
  border-radius: 4px 4px 0 0; background: none; color: var(--color-text-muted); cursor: pointer; }
.gf-tab--active { color: var(--color-accent); background: var(--color-bg-raised, transparent); }
.gf-tab-body { border: 1px solid var(--color-border); border-radius: 0 4px 4px 4px; padding: 14px; }
.gf-preview { border: 1px solid var(--color-border); border-radius: 4px; padding: 8px; margin-top: 12px; }
.gf-gauges { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-start; }
.gf-gauge { border: 1px dashed var(--color-border); border-radius: 4px; padding: 6px 10px; text-align: center; }
.gf-gauge-was { color: var(--color-text-muted); text-decoration: line-through; font-size: 11px; margin-right: 4px; }
.gf-gauge-now { font-size: 16px; }
.gf-gauge-label { display: block; font-size: 9px; letter-spacing: 0.5px; color: var(--color-text-muted); }
.gf-actions { border-top: 1px solid var(--color-border); margin-top: 8px; padding-top: 10px;
  display: flex; align-items: center; gap: 10px; }
.gf-dirty-hint { color: var(--color-text-muted); font-size: 12px; }
.gf-boundary-bar { display: flex; height: 28px; border-radius: 4px; overflow: hidden;
  border: 1px solid var(--color-border); user-select: none; }
.gf-boundary-seg { display: flex; align-items: center; justify-content: center;
  font-size: 9px; letter-spacing: 0.5px; font-weight: 700; color: var(--color-bg, #000); min-width: 0; }
.gf-boundary-divider { width: 5px; cursor: col-resize; background: var(--color-text); opacity: 0.85; }
.gf-boundary-ticks { display: flex; color: var(--color-text-muted); font-size: 10px; margin-top: 3px; }
```

(Check `src/quodeq/ui/src/styles/tokens.css` for the exact variable names — if `--color-bg-raised` or `--font-mono` do not exist, substitute the closest existing token rather than inventing new ones.)

- [ ] **Step 2: `PreviewStrip.jsx`**

```jsx
import { scoreToGradeLabel } from '../../utils/gradeThresholds.js';
import { scoreColorClass } from '../../utils/formatters.js';

function Gauge({ name, before, after }) {
  const changed = before !== after && before != null && after != null;
  const insufficient = after == null;
  return (
    <div className="gf-gauge">
      {changed ? <span className="gf-gauge-was">{before}</span> : null}
      <span className={`gf-gauge-now ${insufficient ? '' : scoreColorClass(after)}`}>
        {insufficient ? '-' : after}
      </span>
      <span className="gf-gauge-label">
        {name.toUpperCase()}
        {insufficient ? ' · INSUFF' : ` · ${(scoreToGradeLabel(after) || '').toUpperCase()}`}
      </span>
    </div>
  );
}

/**
 * Bottom strip: OVERALL + per-dimension before→after gauges, left aligned.
 * preview: {before: {overall, dimensions}, after: {...}} or null.
 */
export default function PreviewStrip({ preview, emptyHint }) {
  if (!preview) {
    return (
      <div className="gf-preview">
        <span className="settings-description">{emptyHint}</span>
      </div>
    );
  }
  const beforeBy = Object.fromEntries(
    (preview.before?.dimensions || []).map((d) => [d.dimension, d.score]),
  );
  const dims = preview.after?.dimensions || [];
  return (
    <div className="gf-preview">
      <div className="gf-gauges">
        <Gauge
          name="overall"
          before={preview.before?.overall?.score}
          after={preview.after?.overall?.score}
        />
        {dims.map((d) => (
          <Gauge key={d.dimension} name={d.dimension} before={beforeBy[d.dimension]} after={d.score} />
        ))}
      </div>
    </div>
  );
}
```

Note the insufficient marker renders a plain `-` (no em-dash in user-facing strings).

- [ ] **Step 3: `useGradeFormula.js`**

```jsx
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  getGradeFormula, saveGradeFormula, resetGradeFormula, previewGradeFormula,
} from '../../api/index.js';
import { setGradeThresholds } from '../../utils/gradeThresholds.js';

const PREVIEW_DEBOUNCE_MS = 250;

/**
 * Grade-formula editor state: server params, dirty draft, debounced preview.
 * projectId: project used for the live preview (may be null).
 */
export default function useGradeFormula(projectId) {
  const [saved, setSaved] = useState(null);     // params dict as saved server-side
  const [draft, setDraft] = useState(null);     // params dict being edited
  const [isCustom, setIsCustom] = useState(false);
  const [defaults, setDefaults] = useState(null);
  const [preview, setPreview] = useState(null); // {before, after} or null
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    getGradeFormula()
      .then((d) => {
        setSaved(d.current); setDraft(d.current);
        setDefaults(d.defaults); setIsCustom(d.isCustom);
      })
      .catch(() => setError('Could not load grade formula'));
  }, []);

  const isDirty = saved && draft && JSON.stringify(saved) !== JSON.stringify(draft);

  const requestPreview = useCallback((params) => {
    if (!projectId) return;
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      previewGradeFormula(projectId, params)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, PREVIEW_DEBOUNCE_MS);
  }, [projectId]);

  // Initial preview once params and project are known.
  useEffect(() => {
    if (draft && projectId) requestPreview(draft);
  }, [projectId, draft === null]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = useCallback((patch) => {
    setDraft((prev) => {
      const next = { ...prev, ...patch };
      requestPreview(next);
      return next;
    });
  }, [requestPreview]);

  const apply = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const d = await saveGradeFormula(draft);
      setSaved(d.current); setDraft(d.current); setIsCustom(d.isCustom);
      setGradeThresholds(d.current.gradeThresholds);
      requestPreview(d.current);
      return d.applied;
    } catch {
      setError('Apply failed');
      return null;
    } finally {
      setBusy(false);
    }
  }, [draft, requestPreview]);

  const resetToDefaults = useCallback(async () => {
    setBusy(true); setError(null);
    try {
      const d = await resetGradeFormula();
      setSaved(d.current); setDraft(d.current); setIsCustom(d.isCustom);
      setGradeThresholds(d.current.gradeThresholds);
      requestPreview(d.current);
    } catch {
      setError('Reset failed');
    } finally {
      setBusy(false);
    }
  }, [requestPreview]);

  return { draft, defaults, isCustom, isDirty, preview, busy, error, update, apply, resetToDefaults };
}
```

- [ ] **Step 4: Build check + commit**

Run: `cd src/quodeq/ui && npm run build`
Expected: success

```bash
git add src/quodeq/ui/src/features/grade-formula src/quodeq/ui/src/styles/base.css
git commit -m "feat(ui): grade-formula slider, preview strip, and editor state hook"
```

---

### Task 12: UI tabs — curve plot, boundary bar, tab bodies

**Files:**
- Create: `src/quodeq/ui/src/features/grade-formula/CurvePlot.jsx`
- Create: `src/quodeq/ui/src/features/grade-formula/GradeBoundaryBar.jsx`
- Create: `src/quodeq/ui/src/features/grade-formula/tabs.jsx`

- [ ] **Step 1: `CurvePlot.jsx`** (presentation only — grade numbers always come from the server preview)

```jsx
const W = 220; const H = 130;
const PAD_L = 26; const PAD_T = 12; const PAD_B = 15;
const PLOT_W = W - PAD_L - 6; const PLOT_H = H - PAD_T - PAD_B;
const MAX_WV = 40;

const x = (wv) => PAD_L + (wv / MAX_WV) * PLOT_W;
const y = (score) => PAD_T + ((10 - score) / 10) * PLOT_H;

function pathFor(fn) {
  const pts = [];
  for (let wv = 0; wv <= MAX_WV; wv += 1) {
    pts.push(`${x(wv).toFixed(1)},${y(Math.max(0, fn(wv))).toFixed(1)}`);
  }
  return `M ${pts.join(' L ')}`;
}

/** Base + ceiling curves with the compliance-lift zone shaded between them. */
export default function CurvePlot({ baseK, ceilScale, thresholds }) {
  const base = (wv) => (wv === 0 ? 10 : 10 / (1 + baseK * wv));
  const ceiling = (wv) => (wv === 0 ? 10 : 10 - Math.log2(1 + wv) * ceilScale);
  const basePath = pathFor(base);
  const ceilPath = pathFor(ceiling);
  const zone = `${ceilPath} L ${x(MAX_WV)},${y(Math.max(0, base(MAX_WV)))} ${
    basePath.slice(2).split(' L ').reverse().join(' L ')} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} role="img" aria-label="Score curves">
      {thresholds.map(([t]) => (
        <line key={t} x1={PAD_L} y1={y(t)} x2={W - 6} y2={y(t)}
          stroke="var(--color-border)" strokeWidth="1" />
      ))}
      {thresholds.map(([t]) => (
        <text key={`t${t}`} x="2" y={y(t) + 3} fontSize="9" fill="var(--color-text-muted)">{t}</text>
      ))}
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={H - PAD_B} stroke="var(--color-border)" />
      <line x1={PAD_L} y1={H - PAD_B} x2={W - 6} y2={H - PAD_B} stroke="var(--color-border)" />
      <path d={zone} fill="var(--color-accent)" opacity="0.12" />
      <path d={ceilPath} fill="none" stroke="var(--color-warning, orange)"
        strokeWidth="1.2" strokeDasharray="4,3" />
      <path d={basePath} fill="none" stroke="var(--color-accent)" strokeWidth="1.8" />
      <text x={W / 2} y={H - 2} fontSize="9" fill="var(--color-text-muted)"
        textAnchor="middle">violations</text>
    </svg>
  );
}
```

(Confirm `--color-warning` exists in `tokens.css`; otherwise use the theme's amber/major-severity token.)

- [ ] **Step 2: `GradeBoundaryBar.jsx`**

```jsx
import { useRef } from 'react';

const SEG_CLASSES = ['grade-bottom', 'grade-low', 'grade-mid', 'grade-high', 'grade-top'];
const SEG_LABELS = ['CRITICAL', 'POOR', 'ADEQUATE', 'GOOD', 'EXEMPLARY'];
const GRADE_COLOR_VARS = [
  'var(--color-grade-bottom-text)', 'var(--color-grade-low-text)',
  'var(--color-grade-mid-text)', 'var(--color-grade-high-text)',
  'var(--color-grade-top-text)',
];
const MIN_GAP = 0.5;

/**
 * Segmented 0-10 bar; thresholds = [[9,'Exemplary'],[7,..],[5,..],[3,..]]
 * (descending). Dragging divider i moves thresholds[3-i] (ascending order
 * left→right). onChange receives a full new thresholds array.
 */
export default function GradeBoundaryBar({ thresholds, onChange }) {
  const barRef = useRef(null);
  // ascending boundary values, e.g. [3,5,7,9]
  const asc = [...thresholds].map(([t]) => t).reverse();
  const edges = [0, ...asc, 10];

  const startDrag = (dividerIdx) => (downEvent) => {
    downEvent.preventDefault();
    const rect = barRef.current.getBoundingClientRect();
    const move = (e) => {
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      let value = ((clientX - rect.left) / rect.width) * 10;
      const lo = (dividerIdx === 0 ? 0 : asc[dividerIdx - 1]) + MIN_GAP;
      const hi = (dividerIdx === asc.length - 1 ? 10 : asc[dividerIdx + 1]) - MIN_GAP;
      value = Math.round(Math.min(hi, Math.max(lo, value)) * 10) / 10;
      const nextAsc = [...asc];
      nextAsc[dividerIdx] = value;
      const desc = [...nextAsc].reverse();
      onChange(thresholds.map(([, label], i) => [desc[i], label]));
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop);
  };

  return (
    <div>
      <div className="gf-boundary-bar" ref={barRef}>
        {edges.slice(0, -1).map((edge, i) => {
          const width = edges[i + 1] - edge;
          return (
            <FragmentSeg key={SEG_LABELS[i]} i={i} width={width} onDrag={startDrag} ascLen={asc.length} />
          );
        })}
      </div>
      <div className="gf-boundary-ticks">
        {edges.slice(0, -1).map((edge, i) => (
          <span key={`tick${i}`} style={{ flex: edges[i + 1] - edge }}>{edge}</span>
        ))}
        <span>10</span>
      </div>
    </div>
  );
}

function FragmentSeg({ i, width, onDrag, ascLen }) {
  return (
    <>
      <div
        className="gf-boundary-seg"
        style={{ flex: width, background: GRADE_COLOR_VARS[i] }}
      >
        {SEG_LABELS[i]}
      </div>
      {i < ascLen ? (
        <div
          className="gf-boundary-divider"
          role="slider"
          aria-label={`Boundary ${i + 1}`}
          onPointerDown={onDrag(i)}
        />
      ) : null}
    </>
  );
}
```

(Check `formatters.js` `GRADE_COLOR_VARS` (~line 80) for the exact CSS variable names and reuse those literals.)

- [ ] **Step 3: `tabs.jsx`** — the four tab bodies

```jsx
import ParamSlider from './ParamSlider.jsx';
import CurvePlot from './CurvePlot.jsx';
import GradeBoundaryBar from './GradeBoundaryBar.jsx';

export function SeverityTab({ draft, update }) {
  const w = draft.severityWeight;
  const setW = (sev) => (v) => update({ severityWeight: { ...w, [sev]: v } });
  const ratio = w.minor > 0 ? Math.round(w.critical / w.minor) : 0;
  return (
    <div>
      <ParamSlider label="critical" value={w.critical} min={0.05} max={10} step={0.05}
        hint="weight of each distinct critical violation type" onChange={setW('critical')} />
      <ParamSlider label="major" value={w.major} min={0.05} max={10} step={0.05}
        hint="weight of each distinct major violation type" onChange={setW('major')} />
      <ParamSlider label="minor" value={w.minor} min={0.05} max={10} step={0.05}
        hint="weight of each distinct minor violation type" onChange={setW('minor')} />
      <span className="settings-description">
        a critical finding currently weighs {ratio}x a minor one
      </span>
    </div>
  );
}

export function CurveTab({ draft, update }) {
  return (
    <div style={{ display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
      <CurvePlot baseK={draft.baseK} ceilScale={draft.ceilScale} thresholds={draft.gradeThresholds} />
      <div style={{ flex: 1, minWidth: 220 }}>
        <ParamSlider label="strictness K" value={draft.baseK} min={0.01} max={1} step={0.01}
          hint="steeper means violations hurt sooner" onChange={(v) => update({ baseK: v })} />
        <ParamSlider label="lift compress" value={draft.liftCompress} min={1} max={4} step={0.1}
          hint="higher means compliance lifts less" onChange={(v) => update({ liftCompress: v })} />
        <ParamSlider label="ceiling scale" value={draft.ceilScale} min={0} max={2} step={0.05}
          hint="higher means a lower max score under violation load"
          onChange={(v) => update({ ceilScale: v })} />
      </div>
    </div>
  );
}

export function BoundariesTab({ draft, update }) {
  return (
    <div>
      <span className="settings-label">GRADE LABELS</span>
      <span className="settings-description"> drag the dividers. These labels drive every gauge and badge in the app.</span>
      <GradeBoundaryBar
        thresholds={draft.gradeThresholds}
        onChange={(t) => update({ gradeThresholds: t })}
      />
      <div style={{ marginTop: 14 }}>
        <span className="settings-label">SEVERITY FLOORS</span>
        <ParamSlider label="minor only" value={draft.floorMinor} min={0} max={10} step={0.5}
          hint="worst score when only minor violations exist"
          onChange={(v) => update({ floorMinor: Math.max(v, draft.floorMajor) })} />
        <ParamSlider label="major" value={draft.floorMajor} min={0} max={10} step={0.5}
          hint="worst score when majors but no criticals exist"
          onChange={(v) => update({ floorMajor: Math.min(v, draft.floorMinor) })} />
        <span className="settings-description">critical: no floor (fixed at 0)</span>
      </div>
    </div>
  );
}

export function DimensionsTab({ draft, update }) {
  const enabled = draft.dimensionWeightsEnabled;
  const weights = draft.dimensionWeights;
  const setDim = (dim) => (v) => update({ dimensionWeights: { ...weights, [dim]: v } });
  return (
    <div>
      <button
        type="button"
        className={`settings-pill${enabled ? ' settings-pill--active' : ''}`}
        aria-pressed={enabled}
        onClick={() => update({ dimensionWeightsEnabled: !enabled })}
      >
        {enabled ? 'weights applied' : 'apply dimension weights'}
      </button>
      <span className="settings-description"> when off, the overall grade is a plain mean across dimensions</span>
      <div style={{ marginTop: 10 }}>
        {Object.entries(weights).map(([dim, w]) => (
          <ParamSlider key={dim} label={dim} value={w} min={0.1} max={3} step={0.1}
            disabled={!enabled} onChange={setDim(dim)} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Build check + commit**

Run: `cd src/quodeq/ui && npm run build`
Expected: success

```bash
git add src/quodeq/ui/src/features/grade-formula
git commit -m "feat(ui): grade-formula tabs with curve plot and draggable boundary bar"
```

---

### Task 13: Page assembly + navigation + boot wiring

**Files:**
- Create: `src/quodeq/ui/src/features/grade-formula/GradeFormulaPage.jsx`
- Modify: `src/quodeq/ui/src/App.jsx` (lazy import ~line 12, `ROUTE_RENDERERS` ~line 255-358, `SettingsCase` ~line 96, boot effect)
- Modify: `src/quodeq/ui/src/features/settings/components/SettingsPage.jsx`

- [ ] **Step 1: `GradeFormulaPage.jsx`**

```jsx
import { useState } from 'react';
import { TermHeader } from '../../components/terminal/index.js';
import useGradeFormula from './useGradeFormula.js';
import PreviewStrip from './PreviewStrip.jsx';
import { SeverityTab, CurveTab, BoundariesTab, DimensionsTab } from './tabs.jsx';

const TABS = [
  { id: 'severity', label: 'SEVERITY', Body: SeverityTab },
  { id: 'curve', label: 'CURVE', Body: CurveTab },
  { id: 'boundaries', label: 'BOUNDARIES', Body: BoundariesTab },
  { id: 'dimensions', label: 'DIMENSIONS', Body: DimensionsTab },
];

export default function GradeFormulaPage({ navigation }) {
  const projectId = navigation?.selectedProject || null;
  const [tab, setTab] = useState('severity');
  const {
    draft, isCustom, isDirty, preview, busy, error, update, apply, resetToDefaults,
  } = useGradeFormula(projectId);

  const onApply = async () => {
    const ok = window.confirm(
      'Apply this formula? All runs and trends will be rescored with the new parameters.',
    );
    if (ok) await apply();
  };

  if (!draft) {
    return (
      <div className="settings-page settings-page--terminal">
        <TermHeader name="grade formula" sub="loading" />
        {error ? <p className="settings-description">{error}</p> : null}
      </div>
    );
  }

  const ActiveBody = TABS.find((t) => t.id === tab).Body;
  return (
    <div className="settings-page settings-page--terminal">
      <TermHeader
        name="grade formula"
        sub={projectId ? `preview: ${projectId}` : 'no project selected for preview'}
      />
      <div className="gf-tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`gf-tab${tab === t.id ? ' gf-tab--active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="gf-tab-body">
        <ActiveBody draft={draft} update={update} />
      </div>
      <PreviewStrip
        preview={preview}
        emptyHint={projectId
          ? 'No evaluation with an event log yet. Run an evaluation to see a live preview.'
          : 'Select a project to see a live preview.'}
      />
      <div className="gf-actions">
        <button type="button" className="settings-pill settings-pill--active"
          disabled={!isDirty || busy} onClick={onApply}>
          APPLY
        </button>
        <button type="button" className="settings-pill" disabled={busy} onClick={resetToDefaults}>
          RESET Q2
        </button>
        <span className="gf-dirty-hint">
          {isDirty ? 'unsaved changes. APPLY rescores all runs.'
            : isCustom ? 'custom formula active' : 'Q2 defaults active'}
        </span>
        {error ? <span className="gf-dirty-hint">{error}</span> : null}
      </div>
      <p className="settings-description" style={{ marginTop: 8 }}>
        These parameters do not affect the insufficient-evidence gate. Principles with too
        little evidence stay Insufficient regardless of formula settings.
      </p>
    </div>
  );
}
```

(Verify `TermHeader`'s import path and props against `SettingsPage.jsx:7,31-34` — identical usage. The RESET Q2 button label uses plain "Q2" because superscript two is fine in docs but the terminal font may lack it; check how the Help section renders Q² (`HelpSections.jsx`) and match it.)

- [ ] **Step 2: Wire `App.jsx`**

Lazy import next to the SettingsPage import (line 12):

```jsx
const GradeFormulaPage = lazy(() => import('./features/grade-formula/GradeFormulaPage.jsx'));
```

`ROUTE_RENDERERS` (after the `settings:` entry at line 354):

```jsx
  settings: (params, props) => <SettingsCase settings={props.settings} onOpenGradeFormula={() => props.navigation.navPush({ page: 'grade-formula' })} />,
  'grade-formula': (params, props) => <GradeFormulaPage navigation={props.navigation} />,
```

`SettingsCase` (line 96) passes the new prop through:

```jsx
function SettingsCase({ settings, onOpenGradeFormula }) {
  return (
    <SettingsPage
      theme={{ mode: settings.themeMode, family: settings.themeFamily, onApplyMode: settings.applyMode, onApplyFamily: settings.applyFamily }}
      onOpenGradeFormula={onOpenGradeFormula}
    />
  );
}
```

Boot-time threshold sync — add inside an existing top-level `useEffect` in the root component (near the health fetch), or a new one:

```jsx
import { getGradeFormula } from './api/index.js';
import { setGradeThresholds } from './utils/gradeThresholds.js';
...
  useEffect(() => {
    getGradeFormula()
      .then((d) => setGradeThresholds(d?.current?.gradeThresholds))
      .catch(() => {});
  }, []);
```

- [ ] **Step 3: Settings entry section (`SettingsPage.jsx`)**

Add a small section between `AppearanceSection` and `AboutSection` (and accept the new prop):

```jsx
export default function SettingsPage({ theme, onOpenGradeFormula }) {
...
        <div className="settings-grid-col">
          <ServerSection />
          <AppearanceSection ... />
          <section className="panel settings-section">
            <div className="settings-row">
              <div className="settings-row-label">
                <span className="settings-label">Grade formula</span>
                <span className="settings-description">
                  Tune how violations and compliance turn into grades. Changes rescore all runs.
                </span>
              </div>
              <button type="button" className="settings-pill" onClick={onOpenGradeFormula}>
                open editor
              </button>
            </div>
          </section>
          <AboutSection ... />
        </div>
```

(Match the exact section/panel markup of `AppearanceSection.jsx` — open it and copy its outer structure including any `SectionLabel`/`panel-header` wrapper so the new section looks native.)

- [ ] **Step 4: Verify in the browser**

Run: `cd src/quodeq/ui && npm run build` then start the app and use the preview tools per project conventions. Manual checks:
1. Settings shows the "Grade formula" row; clicking it pushes the new screen, browser back returns to Settings.
2. Dragging any slider updates the bottom strip within ~300ms (server preview round trip).
3. APPLY confirms, then dashboard gauges reflect the new grades after navigating back.
4. RESET Q2 restores defaults and the strip converges (before == after).
5. The gauge card labels no longer show FAIR anywhere.

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/App.jsx src/quodeq/ui/src/features/settings/components/SettingsPage.jsx src/quodeq/ui/src/features/grade-formula/GradeFormulaPage.jsx
git commit -m "feat(ui): grade formula editor screen wired into settings and nav"
```

---

### Task 14: Docs + full verification

**Files:**
- Modify: `docs/adr/0001-dimension-level-weighting-not-yet-applied.md`
- Modify: `src/quodeq/core/scoring/README.md`
- Modify: `docs/ui-map.md`
- Modify: `src/quodeq/ui/src/features/help/components/HelpSections.jsx:252` (the misleading "weighted average" sentence)

- [ ] **Step 1: Update ADR 0001**

Append a status note (keep the original text for history):

```markdown
## Status update (2026-06-10)

Superseded in part by the Grade Formula Editor
(`docs/superpowers/specs/2026-06-10-grade-formula-editor-design.md`).
Dimension weights are now applied at runtime when the user enables the
"apply dimension weights" switch in Settings > Grade formula
(`ScoringParams.dimension_weights_enabled`). The default remains OFF, so
out-of-the-box behavior is unchanged (plain unweighted mean). Both
aggregation paths (`summarize_dimensions`, `compute_run_score` and the
accumulated view) share `dimension_weighted_average()` from
`core/scoring/params.py`, so they cannot drift apart.
```

- [ ] **Step 2: Update `core/scoring/README.md`**

Add a short "Tunable parameters" section after the formula description:

```markdown
## Tunable parameters

All Q² constants are wrapped by `ScoringParams` (`core/scoring/params.py`).
`DEFAULT_PARAMS` mirrors the constants in `_constants.py`; user overrides
persist at `~/.quodeq/grade_formula.json` (see `services/grade_formula.py`)
and are editable from Settings > Grade formula. Every scoring function takes
an explicit `params` argument — there is no global mutable configuration.
The confidence/insufficient-evidence gate is intentionally NOT part of
`ScoringParams`.
```

- [ ] **Step 3: Update `docs/ui-map.md`**

In §4 Settings table add:

```markdown
| GradeFormulaSection (entry row) | [`SettingsPage.jsx`](../src/quodeq/ui/src/features/settings/components/SettingsPage.jsx) | opens Grade formula editor |
```

Add the screen to the screens catalog (§5 or equivalent):

```markdown
### Grade formula (`grade-formula`)
Pushed from Settings. Tabs: SEVERITY / CURVE / BOUNDARIES / DIMENSIONS.
Bottom strip: before→after preview gauges (latest run of the selected
project, server-computed via POST /api/grade-formula/preview, debounced).
APPLY (confirm) rescores all runs via PUT /api/grade-formula; RESET Q2 via
DELETE. Flow: settings → grade-formula → (apply) → dashboards refetch.
```

- [ ] **Step 4: Fix the Help text**

In `HelpSections.jsx` line ~252, replace the sentence
"The project grade is a weighted average across enabled dimensions."
with:

```
The project grade averages enabled dimensions. Dimension weights apply only when enabled in Settings, Grade formula.
```

- [ ] **Step 5: Full verification**

```bash
export PATH="$HOME/.local/bin:$PATH"
uv run pytest tests/ -q                      # full backend suite
cd src/quodeq/ui && npm run test:all && npm run build
```

Expected: everything green. If `tests/services/scoring/test_projector_scoring.py` parity tests fail, a params default was missed somewhere — diff the two paths' call chains for an unthreaded keyword.

- [ ] **Step 6: Commit docs + final state**

```bash
git add -f docs/adr/0001-dimension-level-weighting-not-yet-applied.md docs/ui-map.md
git add src/quodeq/core/scoring/README.md src/quodeq/ui/src/features/help/components/HelpSections.jsx
git commit -m "docs: grade formula editor (ADR 0001 update, scoring README, ui-map)"
```

- [ ] **Step 7: Final review gate**

Run `git log --oneline develop..HEAD` and confirm one coherent commit series. Then use superpowers:requesting-code-review / finishing-a-development-branch to open the PR against `develop` (title: `feat: grade formula editor with live preview`).
