import json
from pathlib import Path

from codecompass.evaluate.lib.evaluator_loader import load_evaluator


def test_load_evaluator_returns_errors_for_invalid_json(tmp_path: Path):
    path = tmp_path / "evaluator.json"
    path.write_text("{not json")

    evaluator, errors = load_evaluator(path)

    assert evaluator is None
    assert errors
