"""Deterministic verdict computer (v8).

Operates over a VerifierResponse's checklist (Q1-Q4). The model never picks
a verdict; the host system computes it from the checklist answers.

Rule:
  Q1=no                          -> false_positive  (cited code does not match the claim)
  Q2=yes AND Q3=yes              -> false_positive  (override mechanism is visible and grounded)
  Q1=yes AND Q2=no AND Q3=yes    -> confirmed       (claim stands; no override seam in evidence)
  otherwise                      -> inconclusive

Q4 is the model's self-summary and is intentionally ignored for verdict
computation. The audit log keeps it for forensics.
"""

from __future__ import annotations

from quodeq.verifier.models import Verdict, VerifierResponse


def compute_verdict(response: VerifierResponse) -> Verdict:
    q1 = response.checklist["Q1"].answer
    q2 = response.checklist["Q2"].answer
    q3 = response.checklist["Q3"].answer

    if q1 == "no":
        return Verdict.FALSE_POSITIVE
    if q2 == "yes" and q3 == "yes":
        return Verdict.FALSE_POSITIVE
    if q1 == "yes" and q2 == "no" and q3 == "yes":
        return Verdict.CONFIRMED
    return Verdict.INCONCLUSIVE
