from __future__ import annotations

from codecompass.ports.evaluators import EvaluatorsRepository


def resolve_dimension_selection(
    selection: list[str], available: list[str]
) -> tuple[list[str], list[str]]:
    """Return (selected, skipped).

    Dimensions in *selection* that are not in *available* are skipped with a
    warning rather than aborting.  Raises ValueError only when nothing is left.
    """
    if not selection or "all" in selection:
        return available, []

    selected = [d for d in selection if d in available]
    skipped  = [d for d in selection if d not in available]

    if not selected:
        raise ValueError(
            f"None of the requested dimensions are available for this discipline. "
            f"Available: {', '.join(available)}"
        )

    return selected, skipped


def list_available_dimensions(evaluators_repo: EvaluatorsRepository, discipline: str) -> list[str]:
    return sorted(evaluators_repo.list_evaluators(discipline))
