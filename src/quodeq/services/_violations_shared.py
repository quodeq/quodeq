"""Leaf helpers shared by the violation parsers.

``violations_parsing`` (evidence JSON), ``_violations_jsonl`` and
``_violations_stream`` all build the same ``ViolationResponse`` and normalize
raw finding objects the same way; keeping those pieces here means the
sub-modules never import the facade that re-exports them.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from quodeq.core.finding_coercions import coerce_confidence
from quodeq.core.types import Finding, ProgressInfo, ViolationResponse
from quodeq.core.evidence.parser import resolve_llm_refs
from quodeq.services.violation_context import FindingSpec, ViolationContext, build_finding_base

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
        confidence=coerce_confidence(obj.get("confidence")),
        provenance_downgrade=bool(obj.get("provenance_downgrade")),
        scope_downgrade=obj.get("scope_downgrade") if isinstance(obj.get("scope_downgrade"), dict) else None,
        carried_forward=bool(obj.get("carried_forward")),
    ))
    return replace(entry, dimension=obj.get("d", dimension), violation_type=obj.get("vt"))
