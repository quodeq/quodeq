"""Principle map construction: groups findings by principle for detailed views."""

from __future__ import annotations

from typing import Any

from quodeq.core.finding_builder import format_file_line

_DEFAULT_SEVERITY = "minor"
_FINDING_TYPE_VIOLATIONS = "violations"
_FINDING_TYPE_COMPLIANCE = "compliance"


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
            "snippet": item.get("snippet", ""),
            "context": item.get("context"),
            "scope": item.get("scope"),
            "end_line": item.get("end_line"),
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
            entry["reqRefs"] = item["req_refs"]
        principle_map[key][finding_type].append(entry)


def build_principle_map(data: dict[str, Any]) -> dict[str, Any]:
    """Build a mapping from principle name to its aggregated violations/compliance."""
    principle_map: dict[str, Any] = {}
    _seed_principles(data.get("principles", []), principle_map)
    _collect_findings(data.get("violations", []), principle_map, _FINDING_TYPE_VIOLATIONS)
    _collect_findings(data.get("compliance", []), principle_map, _FINDING_TYPE_COMPLIANCE)
    return principle_map
