"""Pure functions translating between FindingsRouter dicts, Judgment, and SQL rows.

The JSONL write path (analysis/mcp/router.py) uses short keys for wire-size
reasons. The runtime Judgment and the SQLite schema use long names. This
module is the only place that knows about both naming conventions.
"""
from __future__ import annotations

import json
from typing import Any

from quodeq.core.events.models import Judgment
from quodeq.core.types.finding import Finding
from quodeq.core.types.req_ref import ReqRef


def _dedup_key(practice_id: str, file: str, line: int, verdict: str) -> str:
    return f"{practice_id}|{file}|{line}|{verdict}"


def _coerce_confidence(value: Any, default: int = 100) -> int:
    """Clamp *value* to [0, 100]; fall back to *default* for missing/non-int."""
    if value is None:
        return default
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    if coerced < 0:
        return 0
    if coerced > 100:
        return 100
    return coerced


def finding_dict_to_row(finding: dict[str, Any]) -> dict[str, Any]:
    """Translate a FindingsRouter wire dict into a row dict ready for SQL bind."""
    practice_id = finding.get("p", "")
    file = finding.get("file", "") or ""
    line = int(finding.get("line", 0) or 0)
    verdict = finding.get("t", "violation")
    refs = finding.get("req_refs")
    return {
        "schema_version": int(finding.get("schema_version", 1)),
        "practice_id": practice_id,
        "dimension": finding.get("d", "") or "",
        "requirement": finding.get("req"),
        "verdict": verdict,
        "severity": finding.get("severity", "medium"),
        "file": file,
        "line": line,
        "end_line": int(finding.get("end_line", 0) or 0),
        "title": finding.get("w", "") or "",
        "reason": finding.get("reason", "") or "",
        "snippet": finding.get("snippet", "") or "",
        # The taxonomy travels as 'vt' on the JSONL wire (see evidence/_jsonl.py);
        # accept the long key too so both spellings survive this seam.
        "violation_type": finding.get("vt") or finding.get("violation_type") or "",
        "context": finding.get("context", "") or "",
        "scope": finding.get("scope", "") or "",
        "req_refs_json": json.dumps(refs) if refs is not None else None,
        "dedup_key": _dedup_key(practice_id, file, line, verdict),
        "confidence": _coerce_confidence(finding.get("confidence")),
        "provenance_downgrade": 1 if finding.get("provenance_downgrade") else 0,
    }


def judgment_to_row(j: Judgment) -> dict[str, Any]:
    """Translate a Judgment into a row dict ready for SQL bind."""
    refs_json: str | None
    if j.req_refs:
        refs_json = json.dumps([{"label": r.label, "url": r.url} for r in j.req_refs])
    else:
        refs_json = "[]"
    return {
        "schema_version": 1,
        "practice_id": j.practice_id,
        "dimension": j.dimension,
        "requirement": j.req,
        "verdict": j.verdict,
        "severity": j.severity,
        "file": j.file,
        "line": j.line,
        "end_line": j.end_line or 0,
        "title": j.title or "",
        "reason": j.reason,
        "snippet": j.snippet or "",
        "violation_type": j.violation_type or "",
        "context": j.context or "",
        "scope": j.scope or "",
        "req_refs_json": refs_json,
        "dedup_key": _dedup_key(j.practice_id, j.file, j.line, j.verdict),
        "confidence": _coerce_confidence(j.confidence),
        "provenance_downgrade": 1 if j.provenance_downgrade else 0,
    }


def row_to_finding(row: dict[str, Any]) -> Finding:
    """Reconstruct a Finding from a SQL row dict."""
    refs_json = row.get("req_refs_json")
    raw_refs: list[dict] = json.loads(refs_json) if refs_json else []
    req_refs = [ReqRef(label=r.get("label", ""), url=r.get("url", "")) for r in raw_refs if isinstance(r, dict)]
    return Finding(
        practice_id=row["practice_id"],
        verdict=row.get("verdict", "violation"),
        file=row.get("file", ""),
        line=row.get("line", 0),
        end_line=row.get("end_line", 0),
        snippet=row.get("snippet", ""),
        severity=row.get("severity", "medium"),
        reason=row.get("reason", ""),
        dimension=row.get("dimension", ""),
        req=row.get("requirement"),
        req_refs=req_refs,
        violation_type=row.get("violation_type", ""),
        title=row.get("title", ""),
        context=row.get("context", ""),
        scope=row.get("scope", ""),
        confidence=_coerce_confidence(row.get("confidence")),
        provenance_downgrade=bool(row.get("provenance_downgrade")),
    )
