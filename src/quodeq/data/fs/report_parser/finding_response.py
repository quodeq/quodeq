"""Finding -> SSE/REST dict shape (wire contract: keys and order frozen)."""
from __future__ import annotations

from typing import Any

from quodeq.core.types.finding import Finding


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
        "provenance_downgrade": f.provenance_downgrade,
        "scope_downgrade": f.scope_downgrade,
    }
