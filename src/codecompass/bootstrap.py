from dataclasses import dataclass

from codecompass.ports.evaluators import EvaluatorsRepository
from codecompass.ports.practices import PracticesRepository


@dataclass(frozen=True)
class DataProvider:
    practices: PracticesRepository
    dimensions: object | None = None
    evaluators: EvaluatorsRepository | None = None
    reports: object | None = None
