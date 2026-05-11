"""Deterministic verdict computer.

Operates over a VerifierResponse's checklist. The model never produces a
verdict; this module produces it from Q3 ∧ Q4 ∧ Q5.
"""

from __future__ import annotations

from quodeq.verifier.models import Verdict, VerifierResponse


def compute_verdict(response: VerifierResponse) -> Verdict:
    """Compute the verdict from the checklist.

    Decision rule:
    - Q3 == yes AND Q4 == yes AND Q5 == yes → false_positive
    - Q3 == no OR Q4 == no → confirmed
    - otherwise → inconclusive
    """
    a3 = response.checklist["Q3"].answer
    a4 = response.checklist["Q4"].answer
    a5 = response.checklist["Q5"].answer

    if a3 == "yes" and a4 == "yes" and a5 == "yes":
        return Verdict.FALSE_POSITIVE
    if a3 == "no" or a4 == "no":
        return Verdict.CONFIRMED
    return Verdict.INCONCLUSIVE
