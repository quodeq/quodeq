"""Persistent storage for dismissed findings -- project-level actions.jsonl.

dismiss_finding() and restore_finding() append events to actions.jsonl.
dismissed_keys() reads the current dismissed state from each run's
evaluation.db (aggregated across runs).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from quodeq.core.events.models import (
    EventType,
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
)
from quodeq.core.types.finding import Finding, SeverityTally, Totals
from quodeq.data.actions_log import ActionLogWriter, read_action_events
from quodeq.data.migrations.dismissed_json_to_actions_log import migrate_if_needed
from quodeq.data.sqlite.connection import open_evaluation_db


def dismiss_finding(project_dir: Path, finding: dict) -> None:
    """Append a FindingDismissed event to project_dir/actions.jsonl."""
    # Fold any legacy dismissed.json in FIRST, so the new event lands after the
    # migrated history rather than the migration appending stale dismissals on
    # top of this action later (see migrate_if_needed).
    migrate_if_needed(project_dir)
    payload = FindingDismissed(
        req=str(finding.get("req", "")),
        file=str(finding.get("file", "")),
        line=int(finding.get("line", 0)),
        reason=finding.get("dismissReason"),
    )
    ActionLogWriter(project_dir).emit(FindingDismissedEvent(payload=payload))


def restore_finding(project_dir: Path, finding: dict) -> None:
    """Append a FindingUndismissed event to project_dir/actions.jsonl."""
    # Fold legacy dismissals in before recording the restore, otherwise the
    # migration would re-dismiss this finding after the fact (ordering bug).
    migrate_if_needed(project_dir)
    payload = FindingUndismissed(
        req=str(finding.get("req", "")),
        file=str(finding.get("file", "")),
        line=int(finding.get("line", 0)),
    )
    ActionLogWriter(project_dir).emit(FindingUndismissedEvent(payload=payload))


def dismissed_keys(project_dir: Path) -> set[tuple]:
    """Return the net set of dismissed (req, file, line) keys for a project.

    Reads ``actions.jsonl`` directly and replays
    ``FINDING_DISMISSED`` / ``FINDING_UNDISMISSED`` in order, so the result
    reflects user intent regardless of whether any individual run has
    been projected into SQL.

    The previous implementation read ``WHERE verdict = 'dismissed'`` from
    each run's ``findings`` table. That broke for older runs that don't
    have an ``events.jsonl``: the findings table stayed empty, so SQL had
    nothing to surface, so rescore saw an empty dismissed set, so the
    score never moved after a dismiss. The actions log is the source of
    truth — the SQL projection is just a downstream view.
    """
    if not project_dir.is_dir():
        return set()

    # Pure-legacy projects (dismissed.json, no actions.jsonl, no events.jsonl)
    # have nothing in the action log until this fold runs. Trigger it at the
    # read seam so the very first score/list after upgrade reflects the user's
    # existing dismissals instead of an empty set.
    migrate_if_needed(project_dir)

    keys: set[tuple] = set()
    for event in read_action_events(project_dir):
        payload = event.payload
        key = (str(payload.req or ""), str(payload.file or ""), int(payload.line or 0))
        if event.event_type == EventType.FINDING_DISMISSED:
            keys.add(key)
        elif event.event_type == EventType.FINDING_UNDISMISSED:
            keys.discard(key)
    return keys


def _enrich_from_sql(run_dir: Path, keys: set[tuple], out: dict[tuple, dict]) -> None:
    """Add finding detail from a run's SQL findings table for any dismissed key not yet enriched.

    Modern runs (those with an ``events.jsonl`` projected into ``findings``)
    expose the full Judgment row here. We look up by the canonical (req,
    file, line) tuple — the SQL ``verdict`` column is ignored because we
    treat ``actions.jsonl`` as the source of truth for *which* findings
    are dismissed, and the SQL row only for *what* the finding was.
    """
    db_path = run_dir / "evaluation.db"
    if not db_path.is_file():
        return
    try:
        with open_evaluation_db(run_dir) as conn:
            cursor = conn.execute(
                "SELECT requirement, file, line, dimension, practice_id, severity, "
                "title, reason, snippet, context, scope, end_line, req_refs_json "
                "FROM findings"
            )
            for row in cursor:
                key = (str(row[0] or ""), str(row[1] or ""), int(row[2] or 0))
                if key not in keys or key in out:
                    continue
                req_refs_raw = row[12]
                try:
                    req_refs = json.loads(req_refs_raw) if req_refs_raw else []
                except (json.JSONDecodeError, TypeError):
                    req_refs = []
                out[key] = {
                    "req": row[0] or "", "file": row[1] or "", "line": row[2] or 0,
                    "dimension": row[3] or "", "principle": row[4] or "",
                    "severity": row[5] or "", "title": row[6] or "", "reason": row[7] or "",
                    "snippet": row[8] or "", "context": row[9] or "", "scope": row[10] or "",
                    "endLine": row[11] or 0, "reqRefs": req_refs,
                }
    except sqlite3.DatabaseError:
        # Corrupt evaluation.db — skip rather than fail the whole list.
        return


def _enrich_from_json_eval(run_dir: Path, keys: set[tuple], out: dict[tuple, dict]) -> None:
    """Add finding detail from a run's ``evaluation/<dim>.json`` files.

    Used for legacy runs that pre-date the event-log scoring engine and so
    never produced a SQL ``findings`` table. The JSON files carry every
    field the Dismissed tab needs (principle, severity, title, reason,
    snippet, context, req_refs); ``dimension`` comes from the filename so
    the entry stays linked to its standard for the restore/delete flows.
    """
    eval_dir = run_dir / "evaluation"
    if not eval_dir.is_dir():
        return
    for path in eval_dir.iterdir():
        if path.suffix != ".json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dimension = path.stem
        for v in (data.get("violations") or []):
            req = str(v.get("req") or "")
            file = str(v.get("file") or "")
            try:
                line = int(v.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
            key = (req, file, line)
            if key not in keys or key in out:
                continue
            out[key] = {
                "req": req, "file": file, "line": line,
                "dimension": dimension, "principle": v.get("principle") or "",
                "severity": v.get("severity") or "", "title": v.get("title") or "",
                "reason": v.get("reason") or "", "snippet": v.get("snippet") or "",
                "context": v.get("context") or "", "scope": v.get("scope") or "",
                "endLine": int(v.get("end_line") or v.get("endLine") or 0),
                "reqRefs": v.get("req_refs") or v.get("reqRefs") or [],
            }


def load_dismissed(
    project_dir: Path,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict]:
    """List dismissed findings as dicts (shape matches /api/findings/dismissed response).

    ``actions.jsonl`` is the source of truth for *which* findings are
    dismissed (via ``dismissed_keys``). The original finding detail is
    looked up from each run's SQL ``findings`` table when the run has been
    projected, with a JSON-eval-file fallback for legacy runs that never
    produced an ``events.jsonl``. Without that fallback, the Dismissed tab
    was permanently empty for any project whose runs pre-date the event-log
    scoring engine — even though the rescore + dismissed-set math always
    worked because both go through ``actions.jsonl``.
    """
    if not project_dir.is_dir():
        return []
    keys = dismissed_keys(project_dir)
    if not keys:
        return []

    details: dict[tuple, dict] = {}
    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        if len(details) >= len(keys):
            break
        _enrich_from_sql(run_dir, keys, details)
        if len(details) >= len(keys):
            break
        _enrich_from_json_eval(run_dir, keys, details)

    items: list[dict] = []
    for req, file, line in keys:
        match = details.get((req, file, line))
        if match is not None:
            items.append(match)
        else:
            # Couldn't find the original finding anywhere — surface a minimal
            # stub so the user can still see (and restore/delete) the entry.
            items.append({
                "req": req, "file": file, "line": line,
                "dimension": "", "principle": "",
                "severity": "", "title": "", "reason": "",
                "snippet": "", "context": "", "scope": "",
                "endLine": 0, "reqRefs": [],
            })

    if offset <= 0 and limit is None:
        return items
    start = max(0, offset)
    end = start + limit if limit is not None and limit >= 0 else None
    return items[start:end]


def restore_all_findings(project_dir: Path) -> int:
    """Append FindingUndismissed events for all currently-dismissed findings.

    Returns the count of restored items.
    """
    keys = dismissed_keys(project_dir)
    count = len(keys)
    if count == 0:
        return 0
    writer = ActionLogWriter(project_dir)
    for req, file, line in keys:
        payload = FindingUndismissed(req=req, file=file, line=line)
        writer.emit(FindingUndismissedEvent(payload=payload))
    return count


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
