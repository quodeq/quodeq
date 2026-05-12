import pytest
from jsonschema import Draft202012Validator, ValidationError
from quodeq.verifier.schema import RESPONSE_SCHEMA


def test_schema_is_valid_json_schema():
    Draft202012Validator.check_schema(RESPONSE_SCHEMA)


def _clean_response():
    return {
        "checklist": {q: {"answer": "yes", "cite": "MANIFEST"} for q in ("Q1", "Q2", "Q3", "Q4")},
        "confidence": 0.8,
        "evidence_summary": "ok",
    }


def test_schema_validates_clean_response():
    Draft202012Validator(RESPONSE_SCHEMA).validate(_clean_response())


def test_schema_rejects_missing_checklist_question():
    resp = _clean_response()
    del resp["checklist"]["Q3"]
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(resp)


def test_schema_rejects_q5_from_v7_2():
    resp = _clean_response()
    resp["checklist"]["Q5"] = {"answer": "yes", "cite": "MANIFEST"}
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(resp)


def test_schema_rejects_legacy_findings_block():
    resp = _clean_response()
    resp["findings"] = {
        "default_implementation": {"value": "X", "cite": None},
        "override_mechanism": {"value": "Y", "cite": None},
        "abstraction_in_use": {"value": "Z", "cite": None},
    }
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(resp)


def test_schema_rejects_unknown_answer_value():
    resp = _clean_response()
    resp["checklist"]["Q1"]["answer"] = "maybe"
    with pytest.raises(ValidationError):
        Draft202012Validator(RESPONSE_SCHEMA).validate(resp)
