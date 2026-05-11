"""Dataclasses for verifier responses, results, and verdicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class Verdict(str, Enum):
    """Computed verdict over a finding."""

    FALSE_POSITIVE = "false_positive"
    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"


# Per-checklist-question answer the model produces.
@dataclass
class ChecklistAnswer:
    answer: Literal["yes", "no", "unknown"]
    cite: str | None  # "file:line" or "MANIFEST" or None


# A single structured-finding extraction (value + cite).
@dataclass
class FindingExtraction:
    value: str | None
    cite: str | None


# All three structured findings the v7.2 prompt requests.
@dataclass
class FindingsExtraction:
    default_implementation: FindingExtraction
    override_mechanism: FindingExtraction
    abstraction_in_use: FindingExtraction


# The model's raw structured response (validated against the JSON Schema).
@dataclass
class VerifierResponse:
    checklist: dict[str, ChecklistAnswer]
    findings: FindingsExtraction
    confidence: float
    evidence_summary: str


# The full audit-trail result returned to the caller.
@dataclass
class VerifierResult:
    verdict: Verdict
    response: VerifierResponse
    consistency_warnings: list[str] = field(default_factory=list)
    model: str = ""
    elapsed_ms: int = 0
