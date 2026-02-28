from typing import Protocol


class EvaluatorsRepository(Protocol):
    def list_evaluators(self, discipline: str) -> list[str]:
        ...

    def get_evaluator(self, discipline: str, dimension: str) -> dict:
        ...
