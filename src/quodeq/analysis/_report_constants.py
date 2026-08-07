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
#
# "Reads" here means two different things, and they don't have to agree:
# a key just needs to be copied into the report JSON to reach the UI (that's
# how `carried_forward` survives from the cache-replay walk to the API and
# the live feed), while scoring itself never reads this JSON at all — it
# reads findings via the SQLite projection and tallies purely on `vt`
# (verdict). So a UI-only signal can live in this tuple without touching a
# grade.
_VIOLATION_FIELDS = (
    "file", "line", "end_line", "title", "reason",
    "snippet", "context", "scope", "severity", "req", "req_refs",
    # _flatten_findings copies ONLY these keys into evaluation/<dim>.json.
    # Without this entry the cache-replay marker is dropped the moment a
    # dimension finishes and its report is written.
    "carried_forward",
    # Same reasoning: without this entry the provenance gate's marker (that it
    # de-escalated the finding from critical to major for naming no external
    # source) is dropped the moment a dimension finishes and its report is
    # written, leaving a downgraded finding indistinguishable from an ordinary
    # major in evaluation/<dim>.json.
    "provenance_downgrade",
    # Same reasoning again for the scope gate's marker, which records WHICH
    # rule capped the finding from major to minor. Without it a waived finding
    # is indistinguishable from an ordinary minor, and the restore-on-tighten
    # path has no `from` to read back.
    "scope_downgrade",
)
_COMPLIANCE_FIELDS = (
    "file", "line", "end_line", "title", "reason",
    "snippet", "context", "scope", "req", "req_refs",
)
_GRADE_INSUFFICIENT = "Insufficient"
