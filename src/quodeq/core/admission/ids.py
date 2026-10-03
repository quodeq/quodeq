"""Requirement id folding: the one rule for matching a near-miss code to a real one."""
from __future__ import annotations

_MIN_REQ_ID_SEGMENTS = 2  # ``<category>-<number>`` is the shortest ID we guess about


def id_shape(req_id: str) -> tuple[str, str] | None:
    """The trailing ``(category, number)`` of a requirement ID, upper-cased.

    ``CLEA-DEP-05`` and ``DEP-05`` both shape to ``("DEP", "05")``. Returns
    None for anything without at least two dash-separated segments ending in
    a number, which is the only form we are willing to guess about.
    """
    parts = [p for p in (req_id or "").strip().split("-") if p]
    if len(parts) < _MIN_REQ_ID_SEGMENTS or not parts[-1].isdigit():
        return None
    return parts[-2].upper(), parts[-1].lstrip("0") or "0"


def normalize_req_id(raw: str, canonical_ids) -> str | None:
    """Fold a near-miss requirement ID onto the standard's real ID.

    Local models emit IDs the standard does not define -- wrong case
    (``CLEa-DEP-05``), a truncated prefix (``CLE-TES-02``) or no prefix at all
    (``SEP-03``). Each is a real finding that would otherwise be quarantined
    over a typo.

    The match is on the trailing ``(category, number)`` pair, so two genuinely
    different requirements can never merge: ``CLEA-DEP-01`` and ``CLEA-DEP-02``
    differ in the number and stay distinct despite being one character apart.
    An ambiguous shape (two canonical IDs sharing the pair) refuses to fold --
    guessing between real requirements is worse than quarantining.
    """
    ids = tuple(canonical_ids or ())
    if not raw or not ids:
        return None
    for candidate in ids:
        if candidate == raw:
            return candidate
    shape = id_shape(raw)
    if shape is None:
        return None
    matches = [c for c in ids if id_shape(c) == shape]
    if len(matches) != 1:
        return None  # unknown, or ambiguous between real requirements
    return matches[0]
