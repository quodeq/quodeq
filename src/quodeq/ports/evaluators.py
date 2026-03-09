"""Port interface for accessing evaluator definitions."""

from typing import Protocol


class EvaluatorsRepository(Protocol):
    """Repository for listing and retrieving evaluator configurations."""
    def list_evaluators(self, discipline: str) -> list[str]:
        """Return the dimension names available for *discipline*."""
        ...

    def get_evaluator(self, discipline: str, dimension: str) -> dict:
        """Return the evaluator mapping document for *dimension* under *discipline*."""
        ...
