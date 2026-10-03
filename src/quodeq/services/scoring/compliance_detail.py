"""Defer finding detail out of the /scores, /scores/<run> and
.../dimensions/<d>/eval payloads.

Violation and compliance items carry ``context``, ``snippet``, ``reason``
and ``reqRefs``, most of the payload's bytes. Only the Principle, File and
Finding pages and the reports render them, so those routes send the items
without those fields (marked ``detailDeferred``) and /compliance-detail
serves them on demand, per kind, from the run's rescored lists (``?asOf=``
for the accumulated lists, ``?run=`` for one run's).
"""
from __future__ import annotations

from typing import Any

from quodeq.core.types.finding_type import FindingType

DETAIL_FIELDS = frozenset({"context", "snippet", "reason", "reqRefs"})
DETAIL_DEFERRED = "detailDeferred"
_LIST_KEY: dict[FindingType, str] = {FindingType.VIOLATION: "violations", FindingType.COMPLIANCE: "compliance"}


def _slim_item(item: dict[str, Any]) -> dict[str, Any]:
    slim = {k: v for k, v in item.items() if k not in DETAIL_FIELDS}
    slim[DETAIL_DEFERRED] = True
    return slim


def defer_dimension_detail(dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*dimensions* with detail dropped from both lists of each; copies every level it changes."""
    return [
        {**dim, **{key: [_slim_item(c) for c in dim.get(key) or []] for key in _LIST_KEY.values()}}
        for dim in dimensions
    ]


def _defer_lists(node: dict[str, Any]) -> dict[str, Any]:
    """*node* with detail dropped from whichever of its two lists it has."""
    return {**node, **{key: [_slim_item(c) for c in node[key]] for key in _LIST_KEY.values() if isinstance(node.get(key), list)}}


def defer_eval_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """A stored dimension eval with detail dropped from its flat lists and
    the per-principle lists left out: they repeat the flat rows in a shape
    (``file:line``, no principle) detail cannot be matched back to, so the
    UI groups the flat rows by principle instead. Keys the payload does
    not have stay absent. Copies every level it changes."""
    deferred = _defer_lists(payload)
    principles = payload.get("principles")
    if isinstance(principles, list):
        deferred["principles"] = [
            {k: v for k, v in p.items() if k not in _LIST_KEY.values()} if isinstance(p, dict) else p
            for p in principles
        ]
    return deferred


def defer_finding_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """*payload* with detail dropped from both accumulated lists.

    Copies every level it changes: the payload can be the accumulated cache's
    own dict, which later requests (including the detail route) read.
    """
    accumulated = payload.get("accumulated")
    if not isinstance(accumulated, dict):
        return payload
    dimensions = defer_dimension_detail(accumulated.get("dimensions") or [])
    return {**payload, "accumulated": {**accumulated, "dimensions": dimensions}}


def finding_detail(
    payload: dict[str, Any], dimension: str, kind: FindingType,
    *, principle: str | None = None, path_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Full items of one kind in one accumulated dimension, in payload order."""
    return dimension_detail(
        (payload.get("accumulated") or {}).get("dimensions") or [], dimension, kind,
        principle=principle, path_prefix=path_prefix)


def dimension_detail(
    dimensions: list[dict[str, Any]], dimension: str, kind: FindingType,
    *, principle: str | None = None, path_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Full items of one kind in the named one of *dimensions*, in payload order."""
    dim = next((d for d in dimensions if d.get("dimension") == dimension), None)
    if dim is None:
        return []
    return [
        c for c in dim.get(_LIST_KEY[kind]) or []
        if (principle is None or c.get("practiceId") == principle)
        and (path_prefix is None or str(c.get("file") or "").startswith(path_prefix))
    ]

