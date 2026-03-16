"""Re-export for backward compatibility — moved to quodeq.core.scoring.internals."""
from quodeq.core.scoring.internals import (  # noqa: F401
    GRADE_LADDER,
    SCALE_TIER_NAMES,
    scale_multiplier,
    tally_types_by_taxonomy,
    tally_types_by_reason,
    evidence_has_taxonomy,
    tally_compliance_types_by_taxonomy,
    tally_compliance_types_by_reason,
    compliance_dampening,
    drop_grade,
    confidence_interval_for,
    score_to_grade_label,
    weight_as_multiplier,
    build_deductions,
    count_grade_drops,
)
