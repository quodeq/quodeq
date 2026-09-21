"""The two rules every enrichment step in ``enricher.py`` repeats.

A sibling rather than more functions in ``enricher.py``: that file sits at
the size ratchet's 300-line cap.
"""
from __future__ import annotations

from quodeq.core.constants import FULL_CONFIDENCE


def apply_downweight(finding: dict[str, object], value: int) -> None:
    """Set *value* as the finding's confidence, unless the model already lowered it.

    A confidence the model emitted below 100 is its own judgement and is left
    alone; an unset or full confidence is what a heuristic downweight is for.
    """
    existing = finding.get("confidence")
    if existing is None or existing == FULL_CONFIDENCE:
        finding["confidence"] = value


def resolve_principle(declared: object, req: object, reqs: dict) -> object:
    """The principle the model declared, or the requirement's when it declared none.

    One rule for both readers of it: the dedup key and the finding's own
    ``p`` field, which would otherwise be free to disagree.
    """
    if not declared and req and req in reqs:
        return reqs[req]["principle"]
    return declared
