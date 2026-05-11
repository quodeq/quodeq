from quodeq.verifier.models import (
    ChecklistAnswer,
    FindingExtraction,
    FindingsExtraction,
    Verdict,
    VerifierResponse,
)
from quodeq.verifier.verdict import compute_verdict


def _resp(answers: dict[str, str]) -> VerifierResponse:
    return VerifierResponse(
        checklist={
            q: ChecklistAnswer(answer=answers.get(q, "unknown"), cite=None)
            for q in ("Q1", "Q2", "Q3", "Q4", "Q5")
        },
        findings=FindingsExtraction(
            default_implementation=FindingExtraction(value=None, cite=None),
            override_mechanism=FindingExtraction(value=None, cite=None),
            abstraction_in_use=FindingExtraction(value=None, cite=None),
        ),
        confidence=0.0,
        evidence_summary="",
    )


def test_all_yes_is_false_positive():
    assert compute_verdict(_resp({q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")})) == Verdict.FALSE_POSITIVE


def test_q3_no_is_confirmed():
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q3"] = "no"
    assert compute_verdict(_resp(answers)) == Verdict.CONFIRMED


def test_q4_no_is_confirmed():
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q4"] = "no"
    assert compute_verdict(_resp(answers)) == Verdict.CONFIRMED


def test_q3_unknown_with_q4q5_yes_is_false_positive():
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q3"] = "unknown"
    assert compute_verdict(_resp(answers)) == Verdict.FALSE_POSITIVE


def test_q4_unknown_with_q3q5_yes_is_false_positive():
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q4"] = "unknown"
    assert compute_verdict(_resp(answers)) == Verdict.FALSE_POSITIVE


def test_q5_unknown_with_q3q4_yes_is_false_positive():
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q5"] = "unknown"
    assert compute_verdict(_resp(answers)) == Verdict.FALSE_POSITIVE


def test_q5_no_with_q3q4_yes_is_inconclusive():
    # Q5=no blocks false_positive (we tolerate unknown, not no), but Q3 and Q4
    # are not the structural-failure questions, so we don't confirm either.
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q5"] = "no"
    assert compute_verdict(_resp(answers)) == Verdict.INCONCLUSIVE


def test_two_unknowns_is_inconclusive():
    answers = {q: "yes" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")}
    answers["Q3"] = "unknown"
    answers["Q4"] = "unknown"
    assert compute_verdict(_resp(answers)) == Verdict.INCONCLUSIVE


def test_all_unknown_is_inconclusive():
    assert compute_verdict(_resp({q: "unknown" for q in ("Q1", "Q2", "Q3", "Q4", "Q5")})) == Verdict.INCONCLUSIVE
