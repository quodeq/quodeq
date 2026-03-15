"""Hybrid repository that tries the web adapter first, falling back to filesystem."""

from __future__ import annotations

from quodeq.shared.types import JsonObject


from quodeq.adapters.hybrid._hybrid_call import hybrid_call
from quodeq.ports.evaluators import EvaluatorsRepository


class HybridEvaluatorsRepository:
    """Evaluators repository that delegates to web then falls back to filesystem."""

    def __init__(self, web: EvaluatorsRepository, fs: EvaluatorsRepository) -> None:
        self._web = web
        self._fs = fs

    def list_evaluators(self, discipline: str) -> list[str]:
        """Return all evaluator names for a discipline, preferring the web source.

        Example::

            repo = HybridEvaluatorsRepository(web=web_repo, fs=fs_repo)
            names = repo.list_evaluators("python")
        """
        return hybrid_call(self._web.list_evaluators, self._fs.list_evaluators, discipline)

    def get_evaluator(self, discipline: str, dimension: str) -> JsonObject:
        """Fetch a single evaluator definition, preferring the web source.

        Example::

            evaluator = repo.get_evaluator("python", "security")
        """
        return hybrid_call(self._web.get_evaluator, self._fs.get_evaluator, discipline, dimension)
