"""Defer compliance detail out of the /scores payload.

Compliance items carry ``context``, ``snippet`` and ``reason``, which made up
~75% of a 28MB /scores payload on a real project. Only the Principle and File
detail pages render them, so /scores sends the items without those fields
(marked ``detailDeferred``) and /compliance-detail serves them on demand from
the same accumulated payload.
"""
from __future__ import annotations

from typing import Any

COMPLIANCE_DETAIL_FIELDS = frozenset({"context", "snippet", "reason"})
DETAIL_DEFERRED = "detailDeferred"


def _slim_item(item: dict[str, Any]) -> dict[str, Any]:
    slim = {k: v for k, v in item.items() if k not in COMPLIANCE_DETAIL_FIELDS}
    slim[DETAIL_DEFERRED] = True
    return slim


def defer_compliance_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """Return *payload* with compliance detail dropped from accumulated dims.

    Copies every level it changes: the payload can be the accumulated cache's
    own dict, which later requests (including /compliance-detail) read.
    """
    accumulated = payload.get("accumulated")
    if not isinstance(accumulated, dict):
        return payload
    dimensions = [
        {**dim, "compliance": [_slim_item(c) for c in dim.get("compliance") or []]}
        for dim in accumulated.get("dimensions") or []
    ]
    return {**payload, "accumulated": {**accumulated, "dimensions": dimensions}}


def compliance_detail(
    payload: dict[str, Any], dimension: str,
    *, principle: str | None = None, path_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Full compliance items of one accumulated dimension, in payload order."""
    dims = (payload.get("accumulated") or {}).get("dimensions") or []
    dim = next((d for d in dims if d.get("dimension") == dimension), None)
    if dim is None:
        return []
    return [
        c for c in dim.get("compliance") or []
        if (principle is None or c.get("practiceId") == principle)
        and (path_prefix is None or str(c.get("file") or "").startswith(path_prefix))
    ]
