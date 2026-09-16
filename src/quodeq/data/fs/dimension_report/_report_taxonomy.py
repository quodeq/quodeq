"""Taxonomy summary for the dimension report (pure helper)."""
from __future__ import annotations

from collections import Counter

from quodeq.core.taxonomy import OTHER

_UNMAPPED_CAP = 50


def unmapped_types(principles: dict) -> list[dict]:
    """[{req, vtRaw, count}] for violations the taxonomy could not place.

    A violation counts when its ``vt`` is missing (untagged) or is the
    reserved ``other`` code (PR B). ``vtRaw`` is the model's spelling so the
    list feeds alias curation. Sorted by count then key; capped at 50 rows.
    """
    counter: Counter[tuple[str, str]] = Counter()
    for pdata in principles.values():
        for v in pdata.get("violations", []):
            vt = v.get("vt")
            if vt and vt != OTHER:
                continue
            counter[(str(v.get("req") or ""), str(v.get("vt_raw") or ""))] += 1
    rows = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"req": req, "vtRaw": raw, "count": n} for (req, raw), n in rows[:_UNMAPPED_CAP]]
