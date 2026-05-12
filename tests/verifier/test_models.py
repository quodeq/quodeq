import pytest
from quodeq.verifier.models import (
    ChecklistAnswer,
    Verdict,
    VerifierResponse,
    VerifierResult,
)


def test_checklist_answer_holds_answer_and_cite():
    a = ChecklistAnswer(answer="yes", cite="MANIFEST")
    assert a.answer == "yes"
    assert a.cite == "MANIFEST"


def test_verifier_response_has_no_findings_field():
    """v8: the structured findings extraction (default_implementation,
    override_mechanism, abstraction_in_use) is gone."""
    resp = VerifierResponse(
        checklist={q: ChecklistAnswer(answer="yes", cite=None) for q in ("Q1", "Q2", "Q3", "Q4")},
        confidence=0.5,
        evidence_summary="",
    )
    assert not hasattr(resp, "findings")


def test_verdict_enum_keeps_not_applicable_value():
    """Verdict.NOT_APPLICABLE is retained so persisted v7.2 records load."""
    assert Verdict.NOT_APPLICABLE.value == "not_applicable"
    assert Verdict.FALSE_POSITIVE.value == "false_positive"
    assert Verdict.CONFIRMED.value == "confirmed"
    assert Verdict.INCONCLUSIVE.value == "inconclusive"


def test_verifier_result_round_trip():
    resp = VerifierResponse(
        checklist={q: ChecklistAnswer(answer="yes", cite=None) for q in ("Q1", "Q2", "Q3", "Q4")},
        confidence=0.9,
        evidence_summary="ok",
    )
    r = VerifierResult(verdict=Verdict.CONFIRMED, response=resp, model="m", elapsed_ms=10)
    assert r.verdict == Verdict.CONFIRMED
    assert r.response.confidence == 0.9


def test_importing_old_findings_classes_fails():
    """v8 removes the structured-findings classes entirely."""
    with pytest.raises(ImportError):
        from quodeq.verifier.models import FindingsExtraction  # noqa: F401
    with pytest.raises(ImportError):
        from quodeq.verifier.models import FindingExtraction  # noqa: F401
