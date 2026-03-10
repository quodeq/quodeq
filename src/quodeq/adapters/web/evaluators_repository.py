"""Web API-backed repository for evaluator configuration files."""
from __future__ import annotations

from quodeq.adapters.web.base_repository import WebRepository


class WebEvaluatorsRepository(WebRepository):
    """Fetch evaluator definitions from a remote HTTP API."""

    def list_evaluators(self, discipline: str) -> list[str]:
        """Retrieve all evaluator names for a discipline from the remote API."""
        return self._get_list(f"/evaluators/{discipline}", "dimensions")

    def get_evaluator(self, discipline: str, dimension_id: str) -> dict:
        """Fetch a single evaluator definition by discipline and dimension from the remote API."""
        return self._get_dict(f"/evaluators/{discipline}/{dimension_id}")
