"""Persistent storage for dismissed findings — per-project JSON file."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.types.finding import Finding, SeverityTally, Totals

_FILENAME = "dismissed.json"


def _dismissed_path(project_dir: Path) -> Path:
    return project_dir / _FILENAME


def _key(entry: dict) -> tuple:
    return (entry.get("req", ""), entry.get("file", ""), entry.get("line", 0))


def load_dismissed(project_dir: Path) -> list[dict]:
    """Load dismissed findings for a project. Returns empty list if none."""
    path = _dismissed_path(project_dir)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def dismiss_finding(project_dir: Path, finding: dict) -> None:
    """Add a finding to the dismissed list. Deduplicates by (req, file, line)."""
    entries = load_dismissed(project_dir)
    new_key = _key(finding)
    if any(_key(e) == new_key for e in entries):
        return
    entry = {
        "req": finding.get("req", ""),
        "file": finding.get("file", ""),
        "line": finding.get("line", 0),
        "dimension": finding.get("dimension", ""),
        "principle": finding.get("principle", ""),
        "severity": finding.get("severity", ""),
        "title": finding.get("title", ""),
        "reason": finding.get("reason", ""),
        "reqRefs": finding.get("reqRefs", []),
        "context": finding.get("context", ""),
        "snippet": finding.get("snippet", ""),
        "scope": finding.get("scope", ""),
        "endLine": finding.get("endLine", 0),
        "dismissed_at": datetime.now(timezone.utc).isoformat(),
    }
    entries.append(entry)
    _dismissed_path(project_dir).write_text(
        json.dumps(entries, indent=2), encoding="utf-8",
    )


def restore_finding(project_dir: Path, finding: dict) -> None:
    """Remove a finding from the dismissed list by (req, file, line)."""
    entries = load_dismissed(project_dir)
    target = _key(finding)
    updated = [e for e in entries if _key(e) != target]
    if len(updated) == len(entries):
        return
    path = _dismissed_path(project_dir)
    if updated:
        path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    elif path.exists():
        path.unlink()


def dismissed_keys(project_dir: Path) -> set[tuple]:
    """Return a set of (req, file, line) tuples for all dismissed findings."""
    return {_key(e) for e in load_dismissed(project_dir)}


def _finding_key(f: Finding) -> tuple:
    return (f.req or "", f.file or "", f.line or 0)


def _recount_totals(violations: list[Finding], old_totals: Totals | None) -> Totals:
    """Recompute totals from a filtered violations list, preserving compliance count."""
    critical = major = minor = unknown = 0
    for v in violations:
        sev = (v.severity or "").lower()
        if sev == "critical":
            critical += 1
        elif sev == "major":
            major += 1
        elif sev == "minor":
            minor += 1
        else:
            unknown += 1
    return Totals(
        violation_count=len(violations),
        compliance_count=old_totals.compliance_count if old_totals else 0,
        severity=SeverityTally(critical=critical, major=major, minor=minor, unknown=unknown),
    )


def filter_dismissed_from_dimensions(
    dimensions: list, project_dir: Path,
) -> list:
    """Return a new list of DimensionResult with dismissed findings removed.

    Recalculates totals for any dimension whose violations were filtered.
    Leaves compliance, principles, overall_score, overall_grade unchanged.
    """
    keys = dismissed_keys(project_dir)
    if not keys:
        return dimensions
    result = []
    for dim in dimensions:
        filtered = [v for v in dim.violations if _finding_key(v) not in keys]
        if len(filtered) == len(dim.violations):
            result.append(dim)
        else:
            result.append(replace(
                dim,
                violations=filtered,
                totals=_recount_totals(filtered, dim.totals),
            ))
    return result
