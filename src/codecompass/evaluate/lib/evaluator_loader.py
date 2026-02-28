from __future__ import annotations

from pathlib import Path
import json

from codecompass.evaluate.lib.evaluator_validator import validate_evaluator


def load_evaluator(path: Path) -> tuple[dict | None, list[str]]:
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        return None, [f"Invalid JSON in {path}: {exc}"]

    errors = validate_evaluator(data)
    return data, errors
