"""Violation and compliance type-counting helpers."""
from __future__ import annotations

import math
from collections import defaultdict

from quodeq.core.scoring._constants import _SEVERITY_WEIGHT


def _tally_types(
    items: list[dict], key_field: str, skip_empty: bool = False,
) -> dict[str, int]:
    """Count distinct types per severity bucket.

    *key_field* selects which dict key to group by (e.g. ``"vt"`` or ``"reason"``).
    When *skip_empty* is ``True``, items whose *key_field* is falsy are ignored.
    """
    buckets: dict[str, set] = {"critical": set(), "major": set(), "minor": set()}
    for item in items:
        value = item.get(key_field)
        if skip_empty and not value:
            continue
        if value is None:
            value = "unknown"
        sev = item.get("severity", "minor")
        buckets.setdefault(sev, set()).add(value)
    return {sev: len(seen) for sev, seen in buckets.items()}


def evidence_has_taxonomy(violations: list[dict]) -> bool:
    """Return True if at least one violation carries a 'vt' field."""
    return any(item.get("vt") for item in violations)


def tally_types_by_taxonomy(violations: list[dict]) -> dict[str, int]:
    """Count distinct violation types per severity using the 'vt' taxonomy field."""
    return _tally_types(violations, "vt", skip_empty=True)


def tally_types_by_reason(violations: list[dict]) -> dict[str, int]:
    """Count distinct violation types per severity using (severity, reason) pairs."""
    return _tally_types(violations, "reason")


def tally_compliance_types_by_taxonomy(compliance: list[dict]) -> dict[str, int]:
    """Count distinct compliance types per severity using the 'vt' field."""
    return _tally_types(compliance, "vt", skip_empty=True)


def tally_compliance_types_by_reason(compliance: list[dict]) -> dict[str, int]:
    """Count distinct compliance types per severity using (severity, reason) pairs."""
    return _tally_types(compliance, "reason")


def _weighted_sum(type_counts: dict[str, int]) -> float:
    """Sum type counts weighted by severity."""
    return sum(
        count * _SEVERITY_WEIGHT.get(sev, 0.25)
        for sev, count in type_counts.items()
    )


def density_weighted_sum(items: list[dict], *, using_taxonomy: bool) -> float:
    """Severity-weighted sum that folds in *instance density* per type.

    The legacy ``_weighted_sum`` only counts the number of *distinct* types
    per severity, so a principle with one violation of type X scores the
    same as one with a hundred violations of type X. That hides bad
    densities (a single rule violated everywhere reads as a single point
    of damage). This variant adds a ``log2(1 + n)`` factor per
    ``(severity, type)`` group so the cost grows with instance count
    without being linear: 1 instance → ×1.0, 10 → ×3.46, 100 → ×6.66.

    *using_taxonomy* selects the grouping key, mirroring the existing
    ``tally_types_by_taxonomy`` / ``tally_types_by_reason`` switch.
    """
    grouped: dict[tuple[str, str], int] = defaultdict(int)
    for item in items:
        sev = item.get("severity", "minor")
        key = item.get("vt") if using_taxonomy else item.get("reason")
        if not key:
            if using_taxonomy:
                continue
            key = "unknown"
        grouped[(sev, key)] += 1
    return sum(
        _SEVERITY_WEIGHT.get(sev, 0.25) * math.log2(1 + n)
        for (sev, _), n in grouped.items()
    )
