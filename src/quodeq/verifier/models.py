"""Dataclasses for verifier responses, results, and verdicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Verdict(str, Enum):
    """Computed verdict over a finding.

    NOT_APPLICABLE is retained for backward compatibility with v7.2 records
    already persisted in verifications.db. The v8 service never produces it.
    """

    FALSE_POSITIVE = "false_positive"
    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"
    NOT_APPLICABLE = "not_applicable"


# Per-checklist-question answer the model produces.
@dataclass
class ChecklistAnswer:
    answer: Literal["yes", "no", "unknown"]
    cite: str | None  # "file:line" or "MANIFEST" or None


# The model's raw structured response (validated against the JSON Schema).
@dataclass
class VerifierResponse:
    checklist: dict[str, ChecklistAnswer]
    confidence: float
    evidence_summary: str


# The full audit-trail result returned to the caller.
@dataclass
class VerifierResult:
    verdict: Verdict
    response: VerifierResponse
    consistency_warnings: list[str] = field(default_factory=list)  # always [] in v8 — retained for serializer compat
    model: str = ""
    elapsed_ms: int = 0
