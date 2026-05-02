"""Persistent storage for dismissed findings — per-project JSON file.

The filesystem implementation below satisfies ``DismissedStoreProtocol``.
To use a different backend (e.g. database), implement that protocol and
wire it in place of the module-level functions.

All read-modify-write operations are protected by a POSIX file lock
(``dismissed.json.lock``) to prevent data corruption from concurrent
API requests or parallel evaluations.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.data._file_lock import lock_file, unlock_file


@runtime_checkable
class DismissedStoreProtocol(Protocol):
    """Abstraction for dismissed-findings storage.

    The default implementation uses per-project JSON files on the
    filesystem (the module-level ``load_dismissed`` / ``dismiss_finding``
    / ``restore_finding`` functions).  Implement this protocol to back
    the store with a database or other persistence layer.
    """

    def load(self, project_dir: Path) -> list[dict]: ...
    def dismiss(self, project_dir: Path, finding: dict) -> None: ...
    def restore(self, project_dir: Path, finding: dict) -> None: ...
    def restore_all(self, project_dir: Path) -> int: ...


_FILENAME = "dismissed.json"


def _dismissed_path(project_dir: Path) -> Path:
    return project_dir / _FILENAME


@contextmanager
def _locked(project_dir: Path):
    """Exclusive file lock for dismissed.json read-modify-write operations."""
    lock_path = project_dir / "dismissed.json.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        lock_file(fd)
        yield
    finally:
        unlock_file(fd)
        os.close(fd)


def _key(entry: dict) -> tuple:
    return (entry.get("req", ""), entry.get("file", ""), entry.get("line", 0))


def load_dismissed(
    project_dir: Path,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict]:
    """Load dismissed findings for a project. Returns empty list if none.

    *offset* and *limit* let API callers slice the result without first
    materializing the full list. The on-disk file is still read in full
    (it's a small per-project JSON), but the returned slice is bounded.
    """
    path = _dismissed_path(project_dir)
    if not path.exists():
        return []
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(items, list):
        return []
    if offset <= 0 and limit is None:
        return items
    start = max(0, offset)
    end = start + limit if limit is not None and limit >= 0 else None
    return items[start:end]


def dismiss_finding(project_dir: Path, finding: dict) -> None:
    """Add a finding to the dismissed list. Deduplicates by (req, file, line)."""
    with _locked(project_dir):
        entries = load_dismissed(project_dir)
        new_key = _key(finding)
        existing_keys = {_key(e) for e in entries}
        if new_key in existing_keys:
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
    with _locked(project_dir):
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


def restore_all_findings(project_dir: Path) -> int:
    """Remove all dismissed findings. Returns the count of restored items."""
    with _locked(project_dir):
        entries = load_dismissed(project_dir)
        count = len(entries)
        if count == 0:
            return 0
        path = _dismissed_path(project_dir)
        if path.exists():
            path.unlink()
        return count


def dismissed_keys(project_dir: Path) -> set[tuple]:
    """Return a set of (req, file, line) tuples for all dismissed findings."""
    return {_key(e) for e in load_dismissed(project_dir)}


def _finding_key(f: Finding) -> tuple:
    return (f.req or "", f.file or "", f.line or 0)


def recount_totals(
    violations: list[Finding],
    compliance_count: int | None = None,
    old_totals: Totals | None = None,
) -> Totals:
    """Recompute totals from a filtered violations list."""
    cc = compliance_count if compliance_count is not None else (old_totals.compliance_count if old_totals else 0)
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
        compliance_count=cc,
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
                totals=recount_totals(filtered, old_totals=dim.totals),
            ))
    return result
