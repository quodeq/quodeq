"""Deterministic verdict computer.

Operates over a VerifierResponse's checklist. The model never produces a
verdict; this module produces it from Q3 ∧ Q4 ∧ Q5.
"""

from __future__ import annotations

from quodeq.verifier.models import Verdict, VerifierResponse


def compute_verdict(response: VerifierResponse) -> Verdict:
    """Compute the verdict from the checklist.

    Decision rule over {Q3, Q4, Q5}:
    - any `no` in Q3 or Q4 → confirmed (definitive contradicting evidence)
    - no `no` anywhere, and at least 2 of the 3 are `yes` → false_positive
      (one `unknown` is tolerated; a definitive `no` is not)
    - otherwise → inconclusive
    """
    answers = [response.checklist[q].answer for q in ("Q3", "Q4", "Q5")]

    if response.checklist["Q3"].answer == "no" or response.checklist["Q4"].answer == "no":
        return Verdict.CONFIRMED
    if "no" not in answers and answers.count("yes") >= 2:
        return Verdict.FALSE_POSITIVE
    return Verdict.INCONCLUSIVE
