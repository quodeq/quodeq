"""Shared helpers and evidence parsing for violation extraction.

Sub-modules :mod:`._violations_jsonl` and :mod:`._violations_stream` handle
JSONL and stream data sources respectively.  Public functions from those
modules are re-exported here for backward compatibility.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from pathlib import Path

from quodeq.core.types import Finding, ProgressInfo, ViolationResponse
from quodeq.core.evidence.parser import resolve_llm_refs
from quodeq.services.violation_context import FindingSpec, ViolationContext, build_finding_base, format_file_line
from quodeq.shared.utils import read_json

# NOTE: logging in inner layer — tracked for middleware extraction
_logger = logging.getLogger(__name__)

_TYPE_VIOLATION = "violation"
_TYPE_COMPLIANCE = "compliance"
_FINDING_TYPES = frozenset({_TYPE_VIOLATION, _TYPE_COMPLIANCE})


@dataclass(frozen=True)
class _ResponseOptions:
    """Keyword-only parameters for _build_violation_response."""
    partial: bool = False
    progress: dict[str, int] | None = None


def _build_violation_response(
    ctx: ViolationContext,
    violations: list[Finding],
    compliance: list[Finding],
    options: _ResponseOptions | None = None,
) -> ViolationResponse:
    """Build the common ViolationResponse for violation/compliance parse results."""
    opts = options or _ResponseOptions()
    progress: ProgressInfo | None = None
    if opts.progress is not None:
        progress = ProgressInfo(
            files_read=opts.progress.get("filesRead", 0),
            violation_count=opts.progress.get("violations", 0),
            compliance_count=opts.progress.get("compliance", 0),
        )
    return ViolationResponse(
        dimension=ctx.dimension,
        run_id=ctx.run_id,
        project=ctx.project,
        violations=violations,
        compliance=compliance,
        partial=opts.partial,
        progress=progress,
    )


def _build_finding_entry(obj: dict, dimension: str, req_refs_lookup: dict[str, list[dict]] | None = None) -> Finding:
    """Build a normalized finding from a raw JSON object."""
    req = obj.get("req")
    # Prefer MCP-enriched req_refs (already filtered to best-match);
    # fall back to compiled-standards lookup + LLM ref selection.
    pre_resolved = obj.get("req_refs")
    if isinstance(pre_resolved, list) and pre_resolved:
        req_refs = pre_resolved
    else:
        all_req_refs = req_refs_lookup.get(req) if req and req_refs_lookup else None
        req_refs = resolve_llm_refs(obj.get("refs"), all_req_refs)
    entry = build_finding_base(FindingSpec(
        practice_id=obj["p"],
        file=obj.get("file"),
        line=obj.get("line"),
        end_line=obj.get("end_line"),
        title=obj.get("w"),
        reason=obj.get("reason"),
        snippet=obj.get("snippet"),
        severity=obj.get("severity"),
        cwe=obj.get("cwe"),
        req=req,
        req_refs=req_refs,
        context=obj.get("context"),
        scope=obj.get("scope"),
        confidence=_coerce_confidence(obj.get("confidence")),
    ))
    return replace(entry, dimension=obj.get("d", dimension), violation_type=obj.get("vt"))


def _coerce_confidence(value: object, default: int = 100) -> int:
    """Clamp a JSONL confidence to [0, 100]; missing/non-int → *default*."""
    if value is None:
        return default
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(100, coerced))


# ---------------------------------------------------------------------------
# Evidence parsing (stays in this module)
# ---------------------------------------------------------------------------

def _build_violation_from_principle(violation: dict, label: str) -> Finding:
    """Build a normalized violation from a principle's violation entry."""
    return build_finding_base(FindingSpec(
        practice_id=label,
        file=format_file_line(violation.get("file"), violation.get("line")),
        line=violation.get("line"),
        title=violation.get("title"),
        reason=violation.get("reason"),
        snippet=violation.get("snippet"),
        severity=violation.get("severity"),
        cwe=violation.get("cwe"),
    ))


def _extract_violations_from_principles(principles: dict) -> list[Finding]:
    """Walk all principles and collect normalized violation findings."""
    violations: list[Finding] = []
    for raw_key, pdata in principles.items():
        label = pdata.get("display_name") or raw_key
        for violation in pdata.get("violations") or []:
            violations.append(_build_violation_from_principle(violation, label))
    return violations


def parse_violations_from_evidence(evidence_path: Path, ctx: ViolationContext) -> ViolationResponse | None:
    """Extract violations from a completed evidence JSON file."""
    try:
        data = read_json(evidence_path)
    except (OSError, json.JSONDecodeError):
        return None
    violations = _extract_violations_from_principles(data.get("principles") or {})
    return _build_violation_response(ctx, violations, [], _ResponseOptions(partial=True))


# ---------------------------------------------------------------------------
# Re-exports for backward compatibility (must stay at bottom to avoid circular imports)
# ---------------------------------------------------------------------------

from quodeq.services._violations_jsonl import parse_violations_from_jsonl  # noqa: E402
from quodeq.services._violations_stream import parse_violations_from_stream  # noqa: E402

__all__ = [
    "parse_violations_from_evidence",
    "parse_violations_from_jsonl",
    "parse_violations_from_stream",
]
