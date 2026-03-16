from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceFileMeta:
    dimension: str
    source_file_count: int | None = None
    date: str | None = None
    discipline: str | None = None
