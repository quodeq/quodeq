"""Report field-name constants shared across report sub-modules."""
from __future__ import annotations

_REPORT_SCHEMA_VERSION = 1

_FIELD_FINAL_SCORE = "finalScore"
_FIELD_FINAL_SCORE_SNAKE = "final_score"
_FIELD_WEIGHTED_SCORE = "weightedScore"
_FIELD_WEIGHTED_SCORE_SNAKE = "weighted_score"
_FIELD_CONFIDENCE_INTERVAL = "confidenceInterval"
_FIELD_CONFIDENCE_INTERVAL_SNAKE = "confidence_interval"

# Fields the report/scoring path reads from a finding. `confidence` is
# intentionally NOT here (#640): it is a UI/triage signal (it drives the
# dashboard's "Low confidence" grouping), not a grade input. Keeping it out
# keeps the grade objective and non-gameable. See tests/core/test_confidence_not_scored.py.
_VIOLATION_FIELDS = (
    "file", "line", "end_line", "title", "reason",
    "snippet", "context", "scope", "severity", "req", "req_refs",
)
_COMPLIANCE_FIELDS = (
    "file", "line", "end_line", "title", "reason",
    "snippet", "context", "scope", "req", "req_refs",
)
_GRADE_INSUFFICIENT = "Insufficient"
