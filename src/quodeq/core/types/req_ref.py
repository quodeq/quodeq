from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReqRef:
    label: str
    url: str
