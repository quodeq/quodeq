"""Header shape of an evidence file, kept apart from the evidence body."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvidenceFileMeta:
    """What an evidence file says about the run that produced it.

    Parsed by ``data.mappers.parse_evidence_file_meta``; only ``dimension``
    is guaranteed, the rest is absent in files written before those fields
    existed.
    """

    dimension: str
    source_file_count: int | None = None
    date: str | None = None
    discipline: str | None = None
