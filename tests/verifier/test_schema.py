import jsonschema

from quodeq.verifier.schema import RESPONSE_SCHEMA


def test_schema_is_valid_json_schema():
    # Will raise SchemaError if the schema itself is malformed
    jsonschema.Draft202012Validator.check_schema(RESPONSE_SCHEMA)


def test_schema_validates_clean_response():
    response = {
        "checklist": {
            "Q1": {"answer": "yes", "cite": "MANIFEST"},
            "Q2": {"answer": "yes", "cite": "src/quodeq/api/app.py:34"},
            "Q3": {"answer": "yes", "cite": "src/quodeq/api/app.py:75"},
            "Q4": {"answer": "yes", "cite": "src/quodeq/services/filesystem.py:39"},
            "Q5": {"answer": "yes", "cite": "src/quodeq/api/app.py:90"},
        },
        "findings": {
            "default_implementation": {"value": "FilesystemActionProvider", "cite": "src/quodeq/api/app.py:36"},
            "override_mechanism": {"value": "param or factory()", "cite": "src/quodeq/api/app.py:90"},
            "abstraction_in_use": {"value": "ActionProvider", "cite": "MANIFEST"},
        },
        "confidence": 1.0,
        "evidence_summary": "Default is FilesystemActionProvider; create_app accepts any ActionProvider.",
    }
    jsonschema.validate(response, RESPONSE_SCHEMA)


def test_schema_rejects_missing_checklist_question():
    response = {
        "checklist": {
            "Q1": {"answer": "yes", "cite": "MANIFEST"},
            # missing Q2-Q5
        },
        "findings": {
            "default_implementation": {"value": None, "cite": None},
            "override_mechanism": {"value": None, "cite": None},
            "abstraction_in_use": {"value": None, "cite": None},
        },
        "confidence": 0.5,
        "evidence_summary": "x",
    }
    try:
        jsonschema.validate(response, RESPONSE_SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("Schema should have rejected missing Q2-Q5")


def test_schema_rejects_unknown_answer_value():
    response = {
        "checklist": {
            "Q1": {"answer": "maybe", "cite": None},  # invalid
            "Q2": {"answer": "yes", "cite": None},
            "Q3": {"answer": "yes", "cite": None},
            "Q4": {"answer": "yes", "cite": None},
            "Q5": {"answer": "yes", "cite": None},
        },
        "findings": {
            "default_implementation": {"value": None, "cite": None},
            "override_mechanism": {"value": None, "cite": None},
            "abstraction_in_use": {"value": None, "cite": None},
        },
        "confidence": 0.0,
        "evidence_summary": "x",
    }
    try:
        jsonschema.validate(response, RESPONSE_SCHEMA)
    except jsonschema.ValidationError:
        return
    raise AssertionError("Schema should have rejected 'maybe'")
