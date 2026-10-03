"""Deterministic check findings go through admission like any other finding."""
from __future__ import annotations

import dataclasses

from quodeq.core.admission import Admitted, FindingFacts, StandardCatalog, admit
from quodeq.core.events.models import Judgment
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
