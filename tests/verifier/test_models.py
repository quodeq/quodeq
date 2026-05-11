from quodeq.verifier.models import (
    ChecklistAnswer,
    FindingExtraction,
    FindingsExtraction,
    Verdict,
    VerifierResponse,
    VerifierResult,
)


def test_verdict_is_enum_like():
    assert Verdict.FALSE_POSITIVE.value == "false_positive"
    assert Verdict.CONFIRMED.value == "confirmed"
    assert Verdict.INCONCLUSIVE.value == "inconclusive"


def test_checklist_answer_required_fields():
    a = ChecklistAnswer(answer="yes", cite="src/foo.py:10")
    assert a.answer == "yes"
    assert a.cite == "src/foo.py:10"


def test_checklist_answer_accepts_manifest_cite():
    a = ChecklistAnswer(answer="yes", cite="MANIFEST")
    assert a.cite == "MANIFEST"


def test_checklist_answer_accepts_null_cite():
    a = ChecklistAnswer(answer="unknown", cite=None)
    assert a.cite is None


def test_finding_extraction_required_fields():
    f = FindingExtraction(value="FooImpl", cite="src/foo.py:8")
    assert f.value == "FooImpl"
    assert f.cite == "src/foo.py:8"


def test_findings_extraction_three_fields():
    f = FindingsExtraction(
        default_implementation=FindingExtraction(value="X", cite="a:1"),
        override_mechanism=FindingExtraction(value="Y", cite="b:2"),
        abstraction_in_use=FindingExtraction(value="Z", cite="MANIFEST"),
    )
    assert f.default_implementation.value == "X"
    assert f.abstraction_in_use.cite == "MANIFEST"


def test_verifier_response_assembly():
    resp = VerifierResponse(
        checklist={
            "Q1": ChecklistAnswer(answer="yes", cite="MANIFEST"),
            "Q2": ChecklistAnswer(answer="yes", cite="app.py:34"),
            "Q3": ChecklistAnswer(answer="yes", cite="app.py:75"),
            "Q4": ChecklistAnswer(answer="yes", cite="filesystem.py:39"),
            "Q5": ChecklistAnswer(answer="yes", cite="app.py:90"),
        },
        findings=FindingsExtraction(
            default_implementation=FindingExtraction(value="FilesystemActionProvider", cite="app.py:36"),
            override_mechanism=FindingExtraction(value="param or factory()", cite="app.py:90"),
            abstraction_in_use=FindingExtraction(value="ActionProvider", cite="MANIFEST"),
        ),
        confidence=1.0,
        evidence_summary="Default is FilesystemActionProvider; create_app accepts any ActionProvider.",
    )
    assert resp.checklist["Q1"].answer == "yes"
    assert resp.confidence == 1.0


def test_verifier_result_carries_audit_trail():
    resp = VerifierResponse(
        checklist={
            "Q1": ChecklistAnswer(answer="yes", cite="MANIFEST"),
            "Q2": ChecklistAnswer(answer="yes", cite="app.py:34"),
            "Q3": ChecklistAnswer(answer="yes", cite="app.py:75"),
            "Q4": ChecklistAnswer(answer="yes", cite="filesystem.py:39"),
            "Q5": ChecklistAnswer(answer="yes", cite="app.py:90"),
        },
        findings=FindingsExtraction(
            default_implementation=FindingExtraction(value="X", cite=None),
            override_mechanism=FindingExtraction(value=None, cite=None),
            abstraction_in_use=FindingExtraction(value="Y", cite="MANIFEST"),
        ),
        confidence=0.7,
        evidence_summary="x",
    )
    result = VerifierResult(
        verdict=Verdict.FALSE_POSITIVE,
        response=resp,
        consistency_warnings=[],
        model="gemma:4",
        elapsed_ms=1234,
    )
    assert result.verdict == Verdict.FALSE_POSITIVE
    assert result.model == "gemma:4"
    assert result.elapsed_ms == 1234
