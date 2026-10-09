"""The stage values behind one principle's score, for the Help page and the Settings editor."""
from __future__ import annotations

from typing import Any

from quodeq.core.scoring.internals import (
    principle_stages, score_to_grade_label, severity_grade_floor, violation_ceiling,
)
from quodeq.core.scoring.mass import PrincipleMass, ViolationRow
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.severity import Severity


def _requirement_entry(row: ViolationRow) -> dict[str, Any]:
    return {
        "req": row.req, "class": row.severity_class,
        "filesAtLeastMinor": row.files_at_least[Severity.MINOR],
        "filesAtLeastMajor": row.files_at_least[Severity.MAJOR],
        "filesAtLeastCritical": row.files_at_least[Severity.CRITICAL],
        "spreadMinor": row.spread_at_least[Severity.MINOR],
        "spreadMajor": row.spread_at_least[Severity.MAJOR],
        "spreadCritical": row.spread_at_least[Severity.CRITICAL],
        "weight": row.weight,
    }


def explain_principle(mass: PrincipleMass, *, params: ScoringParams = DEFAULT_PARAMS) -> dict[str, Any]:
    """Every intermediate of ``principle_score_and_grade`` for one principle."""
    base, lift, raw, final = principle_stages(mass, params=params)
    return {
        "violationRules": len(mass.violations),
        "complianceRules": len(mass.compliance),
        "violationMass": mass.violation_mass,
        "complianceMass": mass.compliance_mass,
        "observation": mass.observation,
        "requirements": [_requirement_entry(r) for r in mass.violations],
        "compliance": [{"req": c.req, "filesOk": c.files_ok, "spread": c.spread} for c in mass.compliance],
        "base": base,
        "lift": lift,
        "raw": raw,
        "ceiling": violation_ceiling(mass.violation_mass, params=params),
        "floor": severity_grade_floor(mass.worst, params=params),
        "final": final,
        "grade": score_to_grade_label(final, params=params),
    }
