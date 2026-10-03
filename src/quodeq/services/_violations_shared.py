"""Leaf helpers shared by the violation parsers.

``violations_parsing`` (evidence JSON), ``_violations_jsonl`` and
``_violations_stream`` all build the same ``ViolationResponse`` and normalize
raw finding objects the same way; keeping those pieces here means the
sub-modules never import the facade that re-exports them.
"""
from __future__ import annotations

from dataclasses import dataclass

from quodeq.core.evidence.jsonl import build_finding_entry  # noqa: F401 -- relocated to core.evidence.jsonl; re-exported for its importers
from quodeq.core.types import Finding, ProgressInfo, ViolationResponse
from quodeq.services.violation_context import ViolationContext


@dataclass(frozen=True)
class ResponseOptions:
    """Keyword-only parameters for build_violation_response."""
    partial: bool = False
    progress: dict[str, int] | None = None


def build_violation_response(
    ctx: ViolationContext,
    violations: list[Finding],
    compliance: list[Finding],
    options: ResponseOptions | None = None,
) -> ViolationResponse:
    """Build the common ViolationResponse for violation/compliance parse results."""
    opts = options or ResponseOptions()
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
