"""Evidence parsing for violation extraction, plus the public parser facade.

The shared helpers live in :mod:`._violations_shared`; sub-modules
:mod:`._violations_jsonl` and :mod:`._violations_stream` handle JSONL and
stream data sources respectively. Public functions from those modules are
re-exported here for backward compatibility.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.types import Finding, ViolationResponse
from quodeq.services._violations_jsonl import parse_violations_from_jsonl
from quodeq.services._violations_shared import (  # noqa: F401 — re-exported patch targets
    FINDING_TYPES,
    TYPE_COMPLIANCE,
    TYPE_VIOLATION,
    ResponseOptions,
    build_finding_entry,
    build_violation_response,
)
from quodeq.services._violations_stream import parse_violations_from_stream
from quodeq.services.violation_context import FindingSpec, ViolationContext, build_finding_base, format_file_line
from quodeq.shared.utils import read_json


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
    except (OSError, ValueError):
        # read_json wraps JSONDecodeError and non-object payloads in ValueError.
        return None
    violations = _extract_violations_from_principles(data.get("principles") or {})
    return build_violation_response(ctx, violations, [], ResponseOptions(partial=True))


__all__ = [
    "parse_violations_from_evidence",
    "parse_violations_from_jsonl",
    "parse_violations_from_stream",
]
