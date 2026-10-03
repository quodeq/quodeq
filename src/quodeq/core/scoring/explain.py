"""The stage values behind one principle's score, for the help page's worked example."""
from __future__ import annotations

from typing import Any

from quodeq.core.scoring._tallies import weighted_sum
from quodeq.core.scoring.internals import (
    principle_stages,
    score_to_grade_label,
    severity_grade_floor,
    violation_ceiling,
)
from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.core.types.severity import Severity

_SEVERITIES = (Severity.CRITICAL, Severity.MAJOR, Severity.MINOR)


def explain_principle(
    vt_counts: dict[str, int], ct_counts: dict[str, int],
    *, params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, Any]:
    """Every intermediate of ``principle_score_and_grade`` for one principle.

    Same functions, same order, so ``final`` and ``grade`` equal what the
    grade tables hold for the same tallies and parameters."""
    base, lift, raw, final = principle_stages(vt_counts, ct_counts, params=params)
    return {
        "types": {str(sev): int(vt_counts.get(sev, 0)) for sev in _SEVERITIES},
        "complianceTypes": int(sum(ct_counts.values())),
        "weightedViolations": weighted_sum(vt_counts, params.severity_weight),
        "base": base,
        "lift": lift,
        "raw": raw,
        "ceiling": violation_ceiling(vt_counts, params=params),
        "floor": severity_grade_floor(vt_counts, params=params),
        "final": final,
        "grade": score_to_grade_label(final, params=params),
    }
