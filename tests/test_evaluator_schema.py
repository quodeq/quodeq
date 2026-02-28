from pathlib import Path


def test_evaluator_schema_exists():
    schema_path = Path("src/codecompass/evaluate/lib/schemas/evaluator.schema.json")
    assert schema_path.is_file()
