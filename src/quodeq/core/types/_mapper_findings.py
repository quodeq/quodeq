"""Mapper functions for finding-related dataclasses."""

from __future__ import annotations

from .finding import Finding, ReqRef, SeverityTally, Totals

from ._mapper_helpers import (
    _bool,
    _int,
    _opt_str,
    _opt_str_or_int,
    _str,
)


def parse_req_ref(raw: dict[str, object]) -> ReqRef:
    return ReqRef(
        label=_str(raw, "label"),
        url=_str(raw, "url"),
    )


def parse_finding(raw: dict[str, object]) -> Finding:
    req_refs_raw = raw.get("reqRefs")
    req_refs: list[ReqRef] = []
    if isinstance(req_refs_raw, list):
        req_refs = [parse_req_ref(r) for r in req_refs_raw if isinstance(r, dict)]

    return Finding(
        principle=_opt_str(raw.get("principle")),
        file=_opt_str(raw.get("file")),
        line=_opt_str_or_int(raw.get("line")),
        title=_opt_str(raw.get("title")),
        reason=_opt_str(raw.get("reason")),
        snippet=_opt_str(raw.get("snippet")),
        severity=_str(raw, "severity", "minor"),
        cwe=_opt_str_or_int(raw.get("cwe")),
        req=_opt_str(raw.get("req")),
        req_refs=req_refs,
        dimension=_opt_str(raw.get("dimension")),
        violation_type=_opt_str(raw.get("violationType")),
    )


def parse_severity_tally(raw: dict[str, object]) -> SeverityTally:
    return SeverityTally(
        critical=_int(raw, "critical"),
        major=_int(raw, "major"),
        minor=_int(raw, "minor"),
        unknown=_int(raw, "unknown"),
    )


def parse_totals(raw: dict[str, object]) -> Totals:
    sev_raw = raw.get("severity")
    severity = parse_severity_tally(sev_raw) if isinstance(sev_raw, dict) else SeverityTally()
    return Totals(
        violation_count=_int(raw, "violationCount"),
        compliance_count=_int(raw, "complianceCount"),
        severity=severity,
    )


def _parse_finding_list(raw_list: object) -> list[Finding]:
    """Parse a list of findings, accepting both dicts and Finding instances."""
    if not isinstance(raw_list, list):
        return []
    result: list[Finding] = []
    for item in raw_list:
        if isinstance(item, Finding):
            result.append(item)
        elif isinstance(item, dict):
            result.append(parse_finding(item))
    return result
