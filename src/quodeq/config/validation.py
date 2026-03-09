"""Validation checks for evaluator configuration files."""

from quodeq.config.paths import ConfigPaths
from quodeq.logging import log_error


def validate_evaluators(discipline: str, paths: ConfigPaths) -> int:
    """Verify that a discipline's evaluators directory exists and contains JSON files."""
    evaluator_dir = paths.evaluators_dir / discipline
    if not evaluator_dir.exists():
        log_error(f"Evaluators directory not found: {evaluator_dir}")
        return 1
    if not any(evaluator_dir.glob("*.json")):
        log_error(f"No evaluator files found in: {evaluator_dir}")
        return 1
    return 0
