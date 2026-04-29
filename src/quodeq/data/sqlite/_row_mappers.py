"""Pure functions translating between FindingsRouter dicts, Judgment, and SQL rows.

The JSONL write path (analysis/mcp/router.py) uses short keys for wire-size
reasons. The runtime Judgment dataclass and the SQLite schema use long names.
This module is the only place that knows about both naming conventions.
"""
from __future__ import annotations

import json
from typing import Any

from quodeq.core.evidence.model import Judgment


def _dedup_key(practice_id: str, file: str, line: int, verdict: str) -> str:
    return f"{practice_id}|{file}|{line}|{verdict}"


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
        "violation_type": finding.get("violation_type", "") or "",
        "context": finding.get("context", "") or "",
        "scope": finding.get("scope", "") or "",
        "req_refs_json": json.dumps(refs) if refs is not None else None,
        "dedup_key": _dedup_key(practice_id, file, line, verdict),
    }


def judgment_to_row(j: Judgment) -> dict[str, Any]:
    """Translate a Judgment dataclass into a row dict ready for SQL bind."""
    return {
        "schema_version": 1,
        "practice_id": j.practice_id,
        "dimension": j.dimension,
        "requirement": j.req,
        "verdict": j.verdict,
        "severity": j.severity,
        "file": j.file,
        "line": j.line,
        "end_line": j.end_line,
        "title": j.title,
        "reason": j.reason,
        "snippet": j.snippet,
        "violation_type": j.violation_type,
        "context": j.context,
        "scope": j.scope,
        "req_refs_json": json.dumps(j.req_refs) if j.req_refs is not None else None,
        "dedup_key": _dedup_key(j.practice_id, j.file, j.line, j.verdict),
    }


def row_to_judgment(row: dict[str, Any]) -> Judgment:
    """Reconstruct a Judgment from a SQL row dict."""
    refs_json = row.get("req_refs_json")
    refs = json.loads(refs_json) if refs_json else None
    return Judgment(
        practice_id=row["practice_id"],
        file=row.get("file", ""),
        line=row.get("line", 0),
        end_line=row.get("end_line", 0),
        snippet=row.get("snippet", ""),
        verdict=row.get("verdict", "violation"),
        severity=row.get("severity", "medium"),
        reason=row.get("reason", ""),
        dimension=row.get("dimension", ""),
        req=row.get("requirement"),
        req_refs=refs,
        violation_type=row.get("violation_type", ""),
        title=row.get("title", ""),
        context=row.get("context", ""),
        scope=row.get("scope", ""),
    )
