from __future__ import annotations

def resolve_dimension_selection(selection: list[str], available: list[str]) -> list[str]:
    if not selection or "all" in selection:
        return available
    for dim in selection:
        if dim not in available:
            raise ValueError(f"Dimension {dim} is not available")
    return selection


def list_available_dimensions(evaluators_repo: object, discipline: str) -> list[str]:
    return sorted(evaluators_repo.list_evaluators(discipline))
