"""Deterministic check findings go through admission like any other finding."""
from __future__ import annotations

import dataclasses

from quodeq.core.admission import Admitted, FindingFacts, StandardCatalog, admit
from quodeq.core.events.models import Judgment
from quodeq.core.evidence.model import Evidence
from quodeq.core.observability import NULL_LOG, LogSink


def admit_all(
    judgments: list[Judgment], rows: list[dict], catalog: StandardCatalog, dimension: str,
    *, log: LogSink = NULL_LOG,
) -> tuple[list[Judgment], list[dict]]:
    """The judgments the standard can place, with principle and requirement set.

    A checker names its requirement in ``practice_id``; admission turns that
    into the canonical requirement and its principle, on the judgment and on
    its wire row alike. One the standard cannot place is dropped from every
    sink, not only from the evidence.
    """
    kept: list[Judgment] = []
    kept_rows: list[dict] = []
    for j, row in zip(judgments, rows):
        placed = admit(FindingFacts.from_wire(row), catalog, dimension)
        if not isinstance(placed, Admitted):
            log.warning(
                f"checks: dropping {j.file} — {j.practice_id!r} is not a requirement "
                f"of {dimension!r} ({placed.reason.value})"
            )
            continue
        kept.append(dataclasses.replace(
            j, practice_id=placed.principle, req=placed.req, dimension=placed.dimension))
        kept_rows.append({**row, "p": placed.principle, "req": placed.req, "d": placed.dimension})
    return kept, kept_rows


def drop_already_reported(
    evidence: Evidence, judgments: list[Judgment], rows: list[dict],
) -> tuple[list[Judgment], list[dict]]:
    """Drop checker violations the model already filed at the same place.

    A CLI agent reads files itself, so it sees a hardcoded key the checker
    also finds and may report it under the same requirement and line.
    Keeping both would count one defect twice.
    """
    kept: list[Judgment] = []
    kept_rows: list[dict] = []
    for j, row in zip(judgments, rows):
        pe = evidence.principles.get(j.practice_id)
        if j.is_violation() and pe is not None and any(
            v.get("req") == j.req and v.get("file") == j.file and v.get("line") == j.line
            for v in pe.violations
        ):
            continue
        kept.append(j)
        kept_rows.append(row)
    return kept, kept_rows
