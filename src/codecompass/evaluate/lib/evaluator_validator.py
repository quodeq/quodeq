from __future__ import annotations

from pathlib import Path
import json
from jsonschema import Draft202012Validator


def _load_schema() -> dict:
    schema_path = Path(__file__).parent / "schemas" / "evaluator.schema.json"
    return json.loads(schema_path.read_text())


def validate_evaluator(evaluator: dict) -> list[str]:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    for error in validator.iter_errors(evaluator):
        path = ".".join([str(p) for p in error.path])
        prefix = f"{path}: " if path else ""
        errors.append(f"{prefix}{error.message}")
    return errors
