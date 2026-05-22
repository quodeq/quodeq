"""Parsers for JSON-format evaluation reports and evidence files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.data.fs.report_parser._totals import build_totals
from quodeq.core.types import Finding
from quodeq.shared.utils import read_json
from quodeq.core.finding_builder import FindingSpec, build_finding_base

_logger = logging.getLogger(__name__)
_CURRENT_SCHEMA_VERSION = 1
_SUPPORTED_SCHEMA_VERSIONS = frozenset({None, _CURRENT_SCHEMA_VERSION})
_EVIDENCE_SUFFIX = "_evidence.json"


def empty_severity_buckets() -> dict[str, list]:
    """Return a fresh ``{critical: [], major: [], minor: []}`` dict."""
    return {"critical": [], "major": [], "minor": []}


def build_finding(item: dict, *, include_severity: bool) -> Finding:
    """Build a normalized finding from a violation or compliance item."""
    return build_finding_base(FindingSpec(
        practice_id=item.get("principle"),
        file=item.get("file"),
        line=item.get("line"),
        end_line=item.get("end_line"),
        title=item.get("title"),
        reason=item.get("reason"),
        snippet=item.get("snippet"),
        severity=item.get("severity"),
        cwe=item.get("cwe"),
        req=item.get("req"),
        req_refs=item.get("req_refs"),
        context=item.get("context"),
        scope=item.get("scope"),
        include_severity=include_severity,
    ))


def parse_report_json(json_path: Path) -> dict[str, Any] | None:
    """Parse a dimension evaluation JSON file into a normalized report dict."""
    try:
        data = read_json(json_path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to parse report %s: %s", json_path.name, exc)
        return None

    sv = data.get("schema_version")
    if sv not in _SUPPORTED_SCHEMA_VERSIONS:
        _logger.warning("Unsupported schema_version %s in %s; attempting best-effort parse", sv, json_path.name)

    violations = [build_finding(v, include_severity=True) for v in data.get("violations", [])]
    compliance = [build_finding(c, include_severity=False) for c in data.get("compliance", [])]

    return {
        "dimension": data.get("dimension"),
        "overallScore": data.get("overallScore"),
        "overallGrade": data.get("overallGrade"),
        # filesRead / sourceFileCount: surface evidence coverage so the
        # dashboard can render a "Partial" badge when a run was deadline-
        # truncated. Pre-Phase-1 reports lack filesRead; the UI treats
        # missing values as "no coverage signal" and skips the badge.
        "filesRead": data.get("filesRead"),
        "sourceFileCount": data.get("sourceFileCount"),
        "principles": [
            {"name": p.get("name"), "score": p.get("score"), "grade": p.get("grade")}
            for p in data.get("principles", [])
        ],
        "detailPrinciples": [],
        "violations": violations,
        "compliance": compliance,
        "totals": build_totals(violations, compliance),
    }


def parse_evidence_file(evidence_path: Path) -> dict[str, Any]:
    """Extract dimension metadata from an evidence JSON file."""
    dimension = evidence_path.name.replace(_EVIDENCE_SUFFIX, "")
    try:
        data = read_json(evidence_path)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to read evidence file %s: %s", evidence_path.name, exc)
        data = {}
    return {
        "dimension": dimension,
        "sourceFileCount": data.get("source_file_count"),
        "date": data.get("date"),
        "discipline": data.get("discipline"),
    }
