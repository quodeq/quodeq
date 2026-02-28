from codecompass.config.paths import ConfigPaths
from codecompass.logging import log_error


def validate_evaluators(discipline: str, paths: ConfigPaths) -> int:
    evaluator_dir = paths.evaluators_dir / discipline
    if not evaluator_dir.exists():
        log_error(f"Evaluators directory not found: {evaluator_dir}")
        return 1
    if not any(evaluator_dir.glob("*.json")):
        log_error(f"No evaluator files found in: {evaluator_dir}")
        return 1
    return 0


# Backward-compatible alias
validate_mappings = validate_evaluators
