"""Parsers for JSON-format evaluation reports and evidence files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from quodeq.adapters.fs.report_parser.grades import build_totals
from quodeq.shared.types import EvidenceFileMeta, FindingDict, ParsedReport, PrincipleGradeWithOverall
from quodeq.shared.utils import TEXT_ENCODING
from quodeq.provider.violation_context import FindingSpec, build_finding_base, format_file_line

_logger = logging.getLogger(__name__)
_CURRENT_SCHEMA_VERSION = 1
_DEFAULT_SEVERITY = "minor"
_SUPPORTED_SCHEMA_VERSIONS = frozenset({None, _CURRENT_SCHEMA_VERSION})
_FINDING_TYPE_VIOLATIONS = "violations"
_FINDING_TYPE_COMPLIANCE = "compliance"
_EVIDENCE_SUFFIX = "_evidence.json"
_OVERALL_PRINCIPLE = "Overall"


def empty_severity_buckets() -> dict[str, list]:
    """Return a fresh ``{critical: [], major: [], minor: []}`` dict."""
    return {"critical": [], "major": [], "minor": []}


def _build_finding(item: dict, *, include_severity: bool) -> dict[str, Any]:
    """Build a normalized finding dict from a violation or compliance item."""
    return build_finding_base(FindingSpec(
        principle=item.get("principle"),
        file=item.get("file"),
        line=item.get("line"),
        title=item.get("title"),
        reason=item.get("reason"),
        snippet=item.get("snippet"),
        severity=item.get("severity"),
        cwe=item.get("cwe"),
        include_severity=include_severity,
    ))


def parse_report_json(json_path: Path) -> ParsedReport | None:
    """Parse a dimension evaluation JSON file into a normalized report dict."""
    try:
        data = json.loads(json_path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to parse report %s: %s", json_path.name, exc)
        return None

    sv = data.get("schema_version")
    if sv not in _SUPPORTED_SCHEMA_VERSIONS:
        _logger.warning("Unsupported schema_version %s in %s; attempting best-effort parse", sv, json_path.name)

    violations = [_build_finding(v, include_severity=True) for v in data.get("violations", [])]
    compliance = [_build_finding(c, include_severity=False) for c in data.get("compliance", [])]

    return {
        "dimension": data.get("dimension"),
        "overallScore": data.get("overallScore"),
        "overallGrade": data.get("overallGrade"),
        "principles": [
            {"name": p.get("name"), "score": p.get("score"), "grade": p.get("grade")}
            for p in data.get("principles", [])
        ],
        "detailPrinciples": [],
        "violations": violations,
        "compliance": compliance,
        "totals": build_totals(violations, compliance),
    }


def parse_evidence_file(evidence_path: Path) -> EvidenceFileMeta:
    """Extract dimension metadata from an evidence JSON file."""
    dimension = evidence_path.name.replace(_EVIDENCE_SUFFIX, "")
    try:
        data = json.loads(evidence_path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to read evidence file %s: %s", evidence_path.name, exc)
        data = {}
    return {
        "dimension": dimension,
        "sourceFileCount": data.get("source_file_count"),
        "date": data.get("date"),
        "discipline": data.get("discipline"),
    }


def _empty_principle(key: str) -> dict:
    """Return a blank principle dict with all expected fields."""
    return {
        "name": key,
        "score": None,
        "grade": None,
        "violations": [],
        "compliance": [],
        "justification": "",
        "recommendations": [],
        "metrics": None,
    }


def _seed_principles(principles: list[dict], principle_map: dict[str, Any]) -> None:
    """Populate principle_map with scored entries from the principles list."""
    for p in principles:
        name = p.get("name", "")
        entry = _empty_principle(name)
        entry["score"] = p.get("score")
        entry["grade"] = p.get("grade")
        principle_map[name] = entry


def _collect_findings(
    items: list[dict], principle_map: dict[str, Any], finding_type: str,
) -> None:
    """Append normalized finding dicts to the appropriate principle entries.

    *finding_type* must be ``"violations"`` or ``"compliance"``.
    """
    for item in items:
        key = item.get("principle", "")
        if key not in principle_map:
            principle_map[key] = _empty_principle(key)
        entry: dict[str, Any] = {
            "code": item.get("snippet", ""),
            "file": format_file_line(item.get("file"), item.get("line")),
            "title": item.get("title", ""),
            "reason": item.get("reason", ""),
        }
        if finding_type == _FINDING_TYPE_VIOLATIONS:
            entry["severity"] = item.get("severity", _DEFAULT_SEVERITY)
        if item.get("cwe"):
            entry["cwe"] = item["cwe"]
        if item.get("req"):
            entry["req"] = item["req"]
        if item.get("req_refs"):
            entry["req_refs"] = item["req_refs"]
        principle_map[key][finding_type].append(entry)


def _build_principle_map(data: dict[str, Any]) -> dict[str, Any]:
    """Build a mapping from principle name to its aggregated violations/compliance."""
    principle_map: dict[str, Any] = {}
    _seed_principles(data.get("principles", []), principle_map)
    _collect_findings(data.get("violations", []), principle_map, _FINDING_TYPE_VIOLATIONS)
    _collect_findings(data.get("compliance", []), principle_map, _FINDING_TYPE_COMPLIANCE)
    return principle_map


def parse_eval_from_json(json_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    """Parse a JSON evaluation file into a detailed report with principle breakdowns."""
    try:
        data = json.loads(json_path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        _logger.warning("Failed to parse evaluation %s: %s", json_path.name, exc)
        return None

    principle_grades = [
        {
            "principle": p.get("name"),
            "score": p.get("score"),
            "grade": p.get("grade"),
            "isOverall": False,
        }
        for p in data.get("principles", [])
    ]
    principle_grades.append(
        {
            "principle": _OVERALL_PRINCIPLE,
            "score": data.get("overallScore"),
            "grade": data.get("overallGrade"),
            "isOverall": True,
        }
    )

    principle_map = _build_principle_map(data)

    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "principleGrades": principle_grades,
        "principles": list(principle_map.values()),
        "violations": data.get("violations", []),
        "compliance": data.get("compliance", []),
        "priorityRemediation": empty_severity_buckets(),
        "rawContent": None,
    }
