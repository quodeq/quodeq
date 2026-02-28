import importlib

from codecompass.evaluate.lib.evaluator_validator import validate_evaluator


def test_jsonschema_available():
    assert importlib.import_module("jsonschema") is not None


def test_validate_evaluator_returns_errors_for_missing_fields():
    errors = validate_evaluator({"metadata": {}})
    assert errors
