"""Violation and compliance type-counting helpers."""
from __future__ import annotations

from typing import Mapping

from quodeq.core.scoring._constants import _SEVERITY_WEIGHT


def evidence_has_taxonomy(violations: list[dict]) -> bool:
    """Return True if at least one violation carries a 'vt' field."""
    return any(item.get("vt") for item in violations)


def _tally_types_fallback(items: list[dict], key_fields: tuple[str, ...]) -> dict[str, int]:
    """Count distinct types per severity, grouping each item by the first
    present key in *key_fields*.

    Unlike taxonomy-only tallying, an item is never dropped: when its preferred
    key (``vt``) is absent it falls back to the next key (``reason``). A single
    tagged finding can therefore no longer flip a principle into a mode that
    discards its untagged findings.
    """
    buckets: dict[str, set] = {"critical": set(), "major": set(), "minor": set()}
    for item in items:
        value = next((item[k] for k in key_fields if item.get(k)), "unknown")
        sev = item.get("severity", "minor")
        buckets.setdefault(sev, set()).add(value)
    return {sev: len(seen) for sev, seen in buckets.items()}


def tally_types(items: list[dict]) -> dict[str, int]:
    """Count distinct violation/compliance types per severity.

    Prefers the stable ``vt`` taxonomy code and falls back to the free-text
    ``reason`` when a finding carries no ``vt``. Because nothing is dropped, the
    result is continuous in taxonomy coverage: 0 tags and 1 tag tally the same,
    and full coverage only sharpens the grouping.
    """
    return _tally_types_fallback(items, ("vt", "reason"))


def _weighted_sum(
    type_counts: dict[str, int],
    severity_weight: Mapping[str, float] | None = None,
) -> float:
    """Sum type counts weighted by severity."""
    weights = severity_weight if severity_weight is not None else _SEVERITY_WEIGHT
    fallback = weights.get("minor", 0.25)
    return sum(
        count * weights.get(sev, fallback)
        for sev, count in type_counts.items()
    )
