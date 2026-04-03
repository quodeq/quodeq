"""Violation and compliance type-counting helpers."""
from __future__ import annotations

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
