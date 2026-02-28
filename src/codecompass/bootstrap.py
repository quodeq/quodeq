from dataclasses import dataclass


@dataclass(frozen=True)
class DataProvider:
    practices: object
    dimensions: object | None = None
    evaluators: object | None = None
    reports: object | None = None
