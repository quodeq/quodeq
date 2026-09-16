"""Coercions for optional per-finding fields that arrive from the wire or JSONL.

Both helpers never raise: a malformed value degrades to the default so a
single bad finding cannot abort a parse (the documented contract of
wire_dict_to_judgment and parse_jsonl_line).
"""
from __future__ import annotations

from quodeq.core._constants import FULL_CONFIDENCE


def coerce_confidence(value: object, default: int = FULL_CONFIDENCE) -> int:
    """Clamp *value* to [0, 100]; fall back to *default* for missing/non-int."""
    if value is None:
        return default
    try:
        coerced = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default
    return max(0, min(FULL_CONFIDENCE, coerced))


def coerce_scope_downgrade(raw: object) -> dict[str, str] | None:
    """Return the scope-gate marker ``{"rule", "from", "to"}`` or None.

    The gate stamps string values only (see scope_gate.py); anything else,
    missing, wrong type, or non-string values, is dropped rather than raised.
    """
    if not isinstance(raw, dict):
        return None
    if not all(isinstance(v, str) for v in raw.values()):
        return None
    return raw
