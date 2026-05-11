from quodeq.verifier.models import (
    ChecklistAnswer,
    FindingExtraction,
    FindingsExtraction,
    VerifierResponse,
)
from quodeq.verifier.validate import (
    citations_resolvable,
    enforce_citation_validity,
    self_consistency_warnings,
)


def _make_response(
    q3_answer="yes", q4_answer="yes", q5_answer="yes",
    override_value="param + fallback",
    override_cite="src/foo.py:90",
    abstraction_value="ActionProvider",
    abstraction_cite="MANIFEST",
    default_value="FilesystemActionProvider",
    default_cite="src/foo.py:36",
) -> VerifierResponse:
    return VerifierResponse(
        checklist={
            "Q1": ChecklistAnswer(answer="yes", cite="MANIFEST"),
            "Q2": ChecklistAnswer(answer="yes", cite="src/foo.py:34"),
            "Q3": ChecklistAnswer(answer=q3_answer, cite="src/foo.py:75"),
            "Q4": ChecklistAnswer(answer=q4_answer, cite="src/foo.py:39"),
            "Q5": ChecklistAnswer(answer=q5_answer, cite="src/foo.py:90"),
        },
        findings=FindingsExtraction(
            default_implementation=FindingExtraction(value=default_value, cite=default_cite),
            override_mechanism=FindingExtraction(value=override_value, cite=override_cite),
            abstraction_in_use=FindingExtraction(value=abstraction_value, cite=abstraction_cite),
        ),
        confidence=1.0,
        evidence_summary="x",
    )


def test_citations_resolvable_accepts_visible_lines():
    visible = {("src/foo.py", 34), ("src/foo.py", 39), ("src/foo.py", 75), ("src/foo.py", 90), ("src/foo.py", 36)}
    resp = _make_response()
    invalid = citations_resolvable(resp, visible)
    assert invalid == []


def test_citations_resolvable_accepts_manifest_token():
    visible: set[tuple[str, int]] = set()  # no L<N> lines
    resp = VerifierResponse(
        checklist={
            "Q1": ChecklistAnswer(answer="yes", cite="MANIFEST"),
            "Q2": ChecklistAnswer(answer="unknown", cite=None),
            "Q3": ChecklistAnswer(answer="unknown", cite=None),
            "Q4": ChecklistAnswer(answer="unknown", cite=None),
            "Q5": ChecklistAnswer(answer="unknown", cite=None),
        },
        findings=FindingsExtraction(
            default_implementation=FindingExtraction(value=None, cite=None),
            override_mechanism=FindingExtraction(value=None, cite=None),
            abstraction_in_use=FindingExtraction(value="Foo", cite="MANIFEST"),
        ),
        confidence=0.0,
        evidence_summary="x",
    )
    assert citations_resolvable(resp, visible) == []


def test_citations_resolvable_flags_unseen_line():
    visible = {("src/foo.py", 34)}  # only one visible line
    resp = _make_response()  # cites several non-visible lines
    invalid = citations_resolvable(resp, visible)
    assert len(invalid) > 0
    assert any("Q3" in item or "Q4" in item or "Q5" in item for item in invalid)


def test_enforce_citation_validity_downgrades_invalid_answers():
    visible = {("src/foo.py", 34), ("src/foo.py", 90)}  # Q5's cite, plus Q2; missing Q3 and Q4
    resp = _make_response()
    cleaned = enforce_citation_validity(resp, visible)
    assert cleaned.checklist["Q2"].answer == "yes"
    assert cleaned.checklist["Q5"].answer == "yes"
    assert cleaned.checklist["Q3"].answer == "unknown"
    assert cleaned.checklist["Q4"].answer == "unknown"
    assert cleaned.checklist["Q3"].cite is None
    assert cleaned.checklist["Q4"].cite is None


def test_self_consistency_passes_when_findings_match_checklist():
    resp = _make_response()
    assert self_consistency_warnings(resp) == []


def test_self_consistency_warns_when_override_present_but_q5_no():
    resp = _make_response(q5_answer="no")
    warnings = self_consistency_warnings(resp)
    assert any("override_mechanism" in w and "Q5" in w for w in warnings)


def test_self_consistency_warns_when_abstraction_present_but_q4_no():
    resp = _make_response(q4_answer="no")
    warnings = self_consistency_warnings(resp)
    assert any("abstraction_in_use" in w and "Q4" in w for w in warnings)
