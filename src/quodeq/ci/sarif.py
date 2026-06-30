"""Build a SARIF 2.1.0 document from Quodeq evaluation reports.

Pure: report dicts in, a SARIF dict out. No I/O. The CLI glue
(`export_cli.py`, `_cli_evaluation.py`) handles loading and writing.
"""
from __future__ import annotations

import re

from quodeq.context.precedent import fingerprint

# quodeq severity -> (SARIF result level, GitHub security-severity string).
# GitHub buckets security-severity: >=9.0 Critical, 7.0-8.9 High,
# 4.0-6.9 Medium, 0.1-3.9 Low. `level` is the separate SARIF axis.
_SEVERITY_MAP: dict[str, tuple[str, str]] = {
    "critical": ("error", "9.0"),
    "major": ("error", "7.0"),
    "high": ("error", "7.0"),
    "minor": ("warning", "4.0"),
}
_DEFAULT_LEVEL_SEVERITY = ("note", "2.0")  # unknown/low/blank

# Ranking used for --min-severity filtering and worst-of rollup.
# Unknown/low/garbage all fall to the default (1).
_RANK = {"critical": 4, "major": 3, "high": 3, "minor": 2}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _severity_level(severity: str | None) -> str:
    return _SEVERITY_MAP.get((severity or "").lower(), _DEFAULT_LEVEL_SEVERITY)[0]


def _security_severity(severity: str | None) -> str:
    return _SEVERITY_MAP.get((severity or "").lower(), _DEFAULT_LEVEL_SEVERITY)[1]


def _severity_rank(severity: str | None) -> int:
    """Higher = more severe. Unknown/blank/garbage all rank lowest (1)."""
    return _RANK.get((severity or "").lower(), 1)


def _slug(text: str | None) -> str:
    return _SLUG_RE.sub("-", (text or "").lower()).strip("-")


def _rule_id(dimension: str | None, principle: str | None) -> str:
    return f"{(dimension or 'unknown').lower()}/{_slug(principle) or 'unknown'}"


def _cwe_tags(req_refs: list[dict] | None) -> list[str]:
    """GitHub-form CWE tags (``external/cwe/cwe-NNN``) from a violation's req_refs.

    GitHub's Security-tab CWE filter reads these from rule.properties.tags.
    Preserves order, de-duplicates, ignores non-CWE labels.
    """
    out: list[str] = []
    seen: set[str] = set()
    for ref in req_refs or []:
        label = str(ref.get("label", "")).strip().lower()
        if not label.startswith("cwe-"):
            continue
        tag = f"external/cwe/{label}"
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _safe_uri(file: str | None) -> str | None:
    """Repo-root-relative POSIX URI, or None if unusable.

    Violation `file` is already repo-root-relative; this only hardens it:
    backslashes -> '/', strip a leading '/', reject blanks and paths that
    escape the root via '..'. Never emits an absolute path.
    """
    if not file:
        return None
    uri = file.replace("\\", "/").lstrip("/")
    if not uri:
        return None
    parts = uri.split("/")
    if ".." in parts:
        return None
    return uri


_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
_INFO_URI = "https://github.com/quodeq/quodeq"


def _message_text(violation: dict) -> str:
    title = str(violation.get("title") or "").strip()
    reason = str(violation.get("reason") or "").strip()
    text = ". ".join(p for p in (title, reason) if p)
    return text or str(violation.get("principle") or "Quodeq finding")


def _location(violation: dict, *, include_snippets: bool) -> dict | None:
    uri = _safe_uri(violation.get("file"))
    if uri is None:
        return None
    region: dict = {}
    line = violation.get("line")
    if isinstance(line, int) and line >= 1:
        region["startLine"] = line
        end = violation.get("end_line")
        if isinstance(end, int) and end >= line:
            region["endLine"] = end
    if include_snippets and violation.get("snippet"):
        region["snippet"] = {"text": str(violation["snippet"])}
    physical: dict = {"artifactLocation": {"uri": uri, "uriBaseId": "SRCROOT"}}
    if region:
        physical["region"] = region
    return {"physicalLocation": physical}


def _result(violation: dict, dimension: str, *, include_snippets: bool) -> dict:
    severity = violation.get("severity") or "unknown"
    result: dict = {
        "ruleId": _rule_id(dimension, violation.get("principle")),
        "level": _severity_level(severity),
        "message": {"text": _message_text(violation)},
        "properties": {
            "quodeq": {
                "dimension": dimension,
                "principle": violation.get("principle"),
                "req": violation.get("req"),
                "severity": severity,
                "cwe": [
                    str(r.get("label"))
                    for r in (violation.get("req_refs") or [])
                    if str(r.get("label", "")).lower().startswith("cwe-")
                ],
            }
        },
    }
    location = _location(violation, include_snippets=include_snippets)
    if location is not None:
        result["locations"] = [location]
    fp = fingerprint(violation.get("req"), violation.get("snippet"))
    if fp:
        result["partialFingerprints"] = {"quodeqReqSnippet/v1": fp}
    return result


def _rule(rule_id: str, principle: str, dimension: str, *, severity: str, cwe_tags: list[str]) -> dict:
    tags = ["quodeq", dimension.lower()]
    if cwe_tags and "security" not in tags:
        tags.append("security")
    tags.extend(t for t in cwe_tags if t not in tags)
    # GitHub soft-caps tags at 10; keep order, trim defensively.
    tags = tags[:10]
    return {
        "id": rule_id,
        "name": principle or rule_id,
        "shortDescription": {"text": principle or rule_id},
        "fullDescription": {"text": f"{dimension.capitalize()} principle: {principle or rule_id}"},
        "helpUri": _INFO_URI,
        "properties": {"tags": tags, "security-severity": _security_severity(severity)},
    }


def build_sarif(
    reports: list[dict],
    *,
    tool_version: str,
    min_severity: str | None = None,
    include_snippets: bool = False,
) -> dict:
    """Build a SARIF 2.1.0 document from Quodeq evaluation reports.

    Violations only (compliance/dismissed excluded). Single run, all
    dimensions merged. Rules are one per (dimension, principle); each rule
    carries the union of its CWEs and a worst-of security-severity. Never
    emits absolute paths or the host `project` field. Deterministic output.
    """
    results: list[dict] = []
    # rule_id -> {"principle", "dimension", "worst_rank", "worst_sev", "cwe_tags"(ordered set)}
    rule_acc: dict[str, dict] = {}

    for report in reports:
        dimension = str(report.get("dimension") or "unknown")
        for violation in report.get("violations") or []:
            if min_severity is not None and _severity_rank(violation.get("severity")) < _severity_rank(min_severity):
                continue
            results.append(_result(violation, dimension, include_snippets=include_snippets))
            rid = _rule_id(dimension, violation.get("principle"))
            acc = rule_acc.setdefault(
                rid,
                {
                    "principle": violation.get("principle") or rid,
                    "dimension": dimension,
                    "worst_rank": -1,
                    "worst_sev": "unknown",
                    "cwe_tags": [],
                },
            )
            rank = _severity_rank(violation.get("severity"))
            if rank > acc["worst_rank"]:
                acc["worst_rank"] = rank
                acc["worst_sev"] = violation.get("severity") or "unknown"
            for tag in _cwe_tags(violation.get("req_refs")):
                if tag not in acc["cwe_tags"]:
                    acc["cwe_tags"].append(tag)

    rules = [
        _rule(rid, acc["principle"], acc["dimension"], severity=acc["worst_sev"], cwe_tags=acc["cwe_tags"])
        for rid, acc in rule_acc.items()
    ]
    rules.sort(key=lambda r: r["id"])
    results.sort(
        key=lambda r: (
            (r.get("locations", [{}])[0].get("physicalLocation", {}).get("artifactLocation", {}).get("uri", "")),
            (r.get("locations", [{}])[0].get("physicalLocation", {}).get("region", {}).get("startLine", 0)),
            r["ruleId"],
        )
    )

    return {
        "$schema": _SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Quodeq",
                        "informationUri": _INFO_URI,
                        "version": tool_version,
                        "semanticVersion": tool_version,
                        "rules": rules,
                    }
                },
                "automationDetails": {"id": "quodeq/scan"},
                "results": results,
                "columnKind": "utf16CodeUnits",
            }
        ],
    }
