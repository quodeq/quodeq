from __future__ import annotations

from codecompass.evaluate.lib.evaluator_validator import validate_evaluator


def build_evaluator(
    *,
    discipline: str,
    dimension: str,
    summary: str,
    principle_practice_map: list,
    requirements_coverage: list,
    metadata: dict,
) -> dict:
    return {
        "metadata": metadata,
        "summary": summary,
        "principle_practice_map": principle_practice_map,
        "requirements_coverage": requirements_coverage,
    }


def validate_and_build_evaluator(**kwargs) -> tuple[dict, list[str]]:
    evaluator = build_evaluator(**kwargs)
    errors = validate_evaluator(evaluator)
    return evaluator, errors
