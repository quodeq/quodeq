"""Violation and compliance type-counting helpers."""
from __future__ import annotations

from typing import Mapping

from quodeq.core.scoring.constants import SEVERITY_WEIGHT
from quodeq.core.types.severity import Severity


def evidence_has_taxonomy(violations: list[dict]) -> bool:
    """Return True if at least one violation carries a 'vt' field."""
    return any(item.get("vt") for item in violations)


def _tally_types_fallback(items: list[dict], key_fields: tuple[str, ...]) -> dict[str, int]:
    """Count distinct types per severity, grouping each item by the first
    present key in *key_fields*.

    Unlike taxonomy-only tallying, an item is never dropped: when its preferred
    key is absent it falls back to the next key in *key_fields*. A single
    tagged finding can therefore no longer flip a principle into a mode that
    discards its untagged findings.
    """
    buckets: dict[str, set] = {"critical": set(), "major": set(), "minor": set()}
    for item in items:
        value = next((item[k] for k in key_fields if item.get(k)), "unknown")
        sev = item.get("severity", Severity.MINOR)
        buckets.setdefault(sev, set()).add(value)
    return {sev: len(seen) for sev, seen in buckets.items()}


def tally_types(items: list[dict]) -> dict[str, int]:
    """Count distinct violation/compliance types per severity.

    Grouping key, first present wins: the ``req`` requirement code every
    finding carries, then the ``vt`` tag, then the free-text ``reason``.
    Nothing is dropped. ``req`` leads because ``vt`` is a tag the model
    invents per finding and paraphrases between runs (seven spellings of
    "magic literal" under one requirement in a single run), so a ``vt``-led
    tally drifted with wording; ``req`` is the stable taxonomy (issue #1274).
    """
    return _tally_types_fallback(items, ("req", "vt", "reason"))


def weighted_sum(
    type_counts: dict[str, int],
    severity_weight: Mapping[str, float] | None = None,
) -> float:
    """Sum type counts weighted by severity."""
    weights = severity_weight if severity_weight is not None else SEVERITY_WEIGHT
    fallback = weights.get("minor", SEVERITY_WEIGHT[Severity.MINOR])
    return sum(
        count * weights.get(sev, fallback)
        for sev, count in type_counts.items()
    )
