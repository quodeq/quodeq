from quodeq.verifier.models import ChecklistAnswer, Verdict, VerifierResponse
from quodeq.verifier.verdict import compute_verdict


def _resp(answers: dict[str, str]) -> VerifierResponse:
    return VerifierResponse(
        checklist={
            q: ChecklistAnswer(answer=answers.get(q, "unknown"), cite=None)
            for q in ("Q1", "Q2", "Q3", "Q4")
        },
        confidence=0.0,
        evidence_summary="",
    )


def test_q1_no_is_false_positive():
    """Cited code doesn't match the claim → claim is broken → false_positive."""
    assert compute_verdict(_resp({"Q1": "no"})) == Verdict.FALSE_POSITIVE


def test_q2_yes_with_q3_yes_is_false_positive():
    """Override mechanism is visible and grounded → claim missed it."""
    assert compute_verdict(_resp({"Q1": "yes", "Q2": "yes", "Q3": "yes"})) == Verdict.FALSE_POSITIVE


def test_full_yes_pattern_is_confirmed():
    """No override seam visible, evidence is grounded → claim stands."""
    assert compute_verdict(_resp({"Q1": "yes", "Q2": "no", "Q3": "yes"})) == Verdict.CONFIRMED


def test_q2_yes_without_q3_yes_is_inconclusive():
    """Override mechanism claimed but evidence not grounded → can't trust."""
    assert compute_verdict(_resp({"Q1": "yes", "Q2": "yes", "Q3": "no"})) == Verdict.INCONCLUSIVE
    assert compute_verdict(_resp({"Q1": "yes", "Q2": "yes", "Q3": "unknown"})) == Verdict.INCONCLUSIVE


def test_q1_unknown_is_inconclusive():
    assert compute_verdict(_resp({"Q1": "unknown", "Q2": "no", "Q3": "yes"})) == Verdict.INCONCLUSIVE


def test_q3_no_with_q1_yes_q2_no_is_inconclusive():
    """We're not sure the no-override conclusion is grounded."""
    assert compute_verdict(_resp({"Q1": "yes", "Q2": "no", "Q3": "no"})) == Verdict.INCONCLUSIVE


def test_all_unknown_is_inconclusive():
    assert compute_verdict(_resp({})) == Verdict.INCONCLUSIVE


def test_q4_is_advisory_does_not_affect_verdict():
    """Q4 is the model's self-summary; verdict ignores it."""
    base = {"Q1": "yes", "Q2": "no", "Q3": "yes"}
    assert compute_verdict(_resp({**base, "Q4": "yes"})) == Verdict.CONFIRMED
    assert compute_verdict(_resp({**base, "Q4": "no"})) == Verdict.CONFIRMED
    assert compute_verdict(_resp({**base, "Q4": "unknown"})) == Verdict.CONFIRMED
