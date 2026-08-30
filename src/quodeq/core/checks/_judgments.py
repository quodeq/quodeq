"""One shape for every deterministic finding.

Checkers are added over time by different hands; without a shared constructor
they drift on severity, confidence and whether a clean result says anything at
all. Those are exactly the fields that decide how a finding scores.
"""
from __future__ import annotations

from quodeq.core.events.models import Judgment, VERDICT_COMPLIANCE, VERDICT_VIOLATION

SEVERITY = "major"
_CONFIDENCE = 100  # a static fact is not a guess


def violation(*, req: str, dimension: str, file: str, line: int,
              title: str, reason: str) -> Judgment:
    return Judgment(
        practice_id=req, req=req, verdict=VERDICT_VIOLATION, dimension=dimension,
        file=file, line=line, title=title, reason=reason,
        severity=SEVERITY, confidence=_CONFIDENCE,
    )


def compliance(*, req: str, dimension: str, anchor: str,
               title: str, reason: str) -> Judgment:
    """A requirement the check covered and found clean.

    Emitting nothing would leave the requirement exactly as unmeasured as it
    was before the checker existed -- "no violations" and "never looked" must
    not read the same. One instance per requirement, not one per file:
    confidence is scored on instance count, and a single traversal has not
    earned more than one.
    """
    return Judgment(
        practice_id=req, req=req, verdict=VERDICT_COMPLIANCE, dimension=dimension,
        file=anchor, line=1, title=title, reason=reason,
        severity=SEVERITY, confidence=_CONFIDENCE,
    )
