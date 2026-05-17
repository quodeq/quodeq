"""Centralized conversions between Finding-shape representations.

This is the only module that knows how to convert between the LLM wire format,
the canonical Judgment, the read-side Finding view, and the API response dict.
SQL row mapping lives in data/sqlite/_row_mappers.py.
"""
from __future__ import annotations

from typing import Any

from quodeq.core.events.models import Judgment
from quodeq.core.types.finding import Finding
from quodeq.core.types.req_ref import ReqRef


def _coerce_req_refs(raw: Any) -> list[ReqRef]:
    if not isinstance(raw, list):
        return []
    refs: list[ReqRef] = []
    for r in raw:
        if isinstance(r, ReqRef):
            refs.append(r)
        elif isinstance(r, dict):
            refs.append(ReqRef(label=r.get("label", ""), url=r.get("url", "")))
    return refs


def wire_dict_to_judgment(d: dict[str, Any]) -> Judgment:
    """Lift a short-key LLM/FindingsRouter wire dict into a Judgment.

    The wire format uses short keys for LLM token economy: p=practice_id,
    t=verdict, d=dimension, w=title. Missing required fields fall back to
    empty strings / 0 so this never raises on malformed input -- the caller
    decides whether to drop the result.
    """
    return Judgment(
        practice_id=d.get("p") or "",
        verdict=d.get("t") or "",
        dimension=d.get("d") or "",
        file=d.get("file") or "",
        line=int(d.get("line") or 0),
        end_line=d.get("end_line"),
        snippet=d.get("snippet"),
        severity=d.get("severity") or "medium",
        violation_type=d.get("violation_type"),
        reason=d.get("reason") or "",
        title=d.get("w"),
        context=d.get("context"),
        scope=d.get("scope"),
        confidence=int(d.get("confidence") if d.get("confidence") is not None else 100),
        req=d.get("req"),
        req_refs=_coerce_req_refs(d.get("req_refs")),
        cwe=d.get("cwe"),
    )


def judgment_to_finding(j: Judgment, *, dismissed: bool = False) -> Finding:
    """Project a Judgment into the read-side Finding view.

    When *dismissed* is True the Finding's verdict becomes "dismissed" --
    Judgment itself never carries that verdict; it's a derived view-only
    state owned by service-layer user-preference logic.
    """
    return Finding(
        practice_id=j.practice_id,
        verdict="dismissed" if dismissed else j.verdict,
        file=j.file,
        line=j.line,
        end_line=j.end_line,
        title=j.title,
        reason=j.reason,
        snippet=j.snippet,
        severity=j.severity or "minor",
        cwe=j.cwe,
        req=j.req,
        req_refs=list(j.req_refs),
        context=j.context,
        dimension=j.dimension,
        violation_type=j.violation_type,
        scope=j.scope,
        confidence=j.confidence,
    )


def finding_to_response_dict(f: Finding) -> dict[str, Any]:
    """Render a Finding as the dict shape expected by SSE and REST clients."""
    req_refs = (
        [{"label": r.label, "url": r.url} for r in f.req_refs]
        if f.req_refs else None
    )
    return {
        "practice_id": f.practice_id,
        "file": f.file,
        "line": f.line,
        "end_line": f.end_line,
        "snippet": f.snippet,
        "verdict": f.verdict,
        "severity": f.severity,
        "reason": f.reason,
        "title": f.title,
        "req": f.req,
        "req_refs": req_refs,
    }
