"""One shape for every deterministic finding.

Checkers are added over time by different hands; without a shared constructor
they drift on severity, confidence and whether a clean result says anything at
all. Those are exactly the fields that decide how a finding scores.
"""
from __future__ import annotations

import dataclasses

from quodeq.core.checks.model import SourceLocation
from quodeq.core.events.models import Judgment
from quodeq.core.types.finding_type import FindingType
from quodeq.core.constants import FULL_CONFIDENCE
from quodeq.core.types.severity import Severity

SEVERITY = Severity.MAJOR


def violation(*, req: str, dimension: str, at: SourceLocation,
              title: str, reason: str) -> Judgment:
    return Judgment(
        practice_id=req, req=req, verdict=FindingType.VIOLATION, dimension=dimension,
        file=at.file, line=at.line, title=title, reason=reason,
        severity=SEVERITY, confidence=FULL_CONFIDENCE,  # a static fact is not a guess
    )


def critical(judgment: Judgment, *, snippet: str, violation_type: str) -> Judgment:
    """*judgment* as a violation exploitable as written, such as a credential
    in the repo. *snippet* must already be masked: it is stored as is."""
    return dataclasses.replace(
        judgment, severity=Severity.CRITICAL, snippet=snippet, violation_type=violation_type,
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
        practice_id=req, req=req, verdict=FindingType.COMPLIANCE, dimension=dimension,
        file=anchor, line=1, title=title, reason=reason,
        severity=SEVERITY, confidence=FULL_CONFIDENCE,  # a static fact is not a guess
    )
