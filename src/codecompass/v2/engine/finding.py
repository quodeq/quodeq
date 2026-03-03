from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Finding:
    rule: str
    label: str
    file: str
    dimension: str
    detector: str
    cwe: int | None = None
    line: int | None = None
    snippet: str | None = None
    severity_hint: str = "medium"

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}
