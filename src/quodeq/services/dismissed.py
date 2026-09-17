"""Persistent storage for dismissed findings -- project-level actions.jsonl.

dismiss_finding() and restore_finding() append events to actions.jsonl.
dismissed_keys() folds the log into the project's net ``DismissedKeys``
(``core.dismissals``): a dismissal is identified by its snippet fingerprint
and survives the line shifts every refactor causes; the line is kept as a
display hint and as the identity of snippet-less findings. The Dismissed tab
listing lives in ``services/_dismissed_listing``.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from quodeq.core.dismissals import (
    EMPTY_DISMISSED,
    DismissedEntry,
    DismissedKeys,
    fold_dismissals,
)
from quodeq.data.ports.actions_log import ActionLog
from quodeq.services._dismiss_fingerprints import backfill_if_needed, resolve_fingerprint
from quodeq.services._wiring import (
    ActionLogWriter,
    load_suppression_rules,
    migrate_if_needed,
    read_action_events,
)
from quodeq.services.suppression_keys import is_dismissed
from quodeq.core.events.models import (
    FindingDismissed,
    FindingDismissedEvent,
    FindingUndismissed,
    FindingUndismissedEvent,
)
from quodeq.core.evidence.model import violations_per_100_files
from quodeq.core.types.finding import Finding, SeverityTally, Totals


def _target_of(finding: dict) -> DismissedEntry:
    """The ``(req, file, line)`` a client names, as an unfingerprinted entry."""
    raw_line = finding.get("line", 0)
    try:
        line = int(raw_line)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"finding.line must be an integer, got {raw_line!r}") from exc
    return DismissedEntry(str(finding.get("req", "")), str(finding.get("file", "")), line)


def undismiss_event(entry: DismissedEntry) -> FindingUndismissedEvent:
    """The event that releases *entry*: by fingerprint when it has one, else by line."""
    return FindingUndismissedEvent(payload=FindingUndismissed(
        req=entry.req, file=entry.file, line=entry.line, fingerprint=entry.fingerprint))


def dismiss_finding(
    project_dir: Path, finding: dict, *, writer: ActionLog | None = None,
    run_id: str | None = None,
) -> None:
    """Append a FindingDismissed event to project_dir/actions.jsonl.

    The fingerprint is resolved server-side from the finding's stored snippet
    (*run_id*'s findings first, then every run newest first, then the
    client's ``snippet`` field) so the recorded identity always matches what
    the projection hashes from the same rows.
    """
    # Fold any legacy dismissed.json in FIRST, so the new event lands after the
    # migrated history rather than the migration appending stale dismissals on
    # top of this action later (see migrate_if_needed).
    migrate_if_needed(project_dir)
    target = _target_of(finding)
    payload = FindingDismissed(
        req=target.req,
        file=target.file,
        line=target.line,
        reason=finding.get("dismissReason"),
        fingerprint=resolve_fingerprint(
            project_dir, target, run_id=run_id, snippet=finding.get("snippet")),
    )
    log = writer or ActionLogWriter(project_dir)
    log.emit(FindingDismissedEvent(payload=payload))


def _undismiss_targets(
    project_dir: Path, state: DismissedKeys, finding: dict,
) -> list[DismissedEntry]:
    """The entries whose release restores the finding the client named.

    The client's ``fingerprint`` (from the dismissed listing) names the entry
    exactly. Without it, the entries recorded at ``(req, file, line)`` are
    restored -- fingerprinted ones by fingerprint, so a finding that has since
    moved is released everywhere. A finding no entry was recorded at (an
    older client naming a moved finding by its new line) is fingerprinted
    from its stored snippet so the entry still resolves.
    """
    target = _target_of(finding)
    req, file, line = target.line_key
    client_fp = finding.get("fingerprint") or None
    if client_fp:
        for entry in state.entries:
            if entry.req == req and entry.file == file and entry.fingerprint == client_fp:
                return [DismissedEntry(req, file, entry.line, client_fp)]
    at_line = state.entries_at(req, file, line)
    fingerprinted = [e.fingerprint for e in at_line if e.fingerprint]
    if fingerprinted:
        return [DismissedEntry(req, file, line, fp) for fp in fingerprinted]
    if at_line:
        return [DismissedEntry(req, file, line)]
    fp = resolve_fingerprint(project_dir, target, snippet=finding.get("snippet"))
    return [DismissedEntry(req, file, line, fp)]


def restore_finding(project_dir: Path, finding: dict, *, writer: ActionLog | None = None) -> None:
    """Append the FindingUndismissed event(s) to project_dir/actions.jsonl in one write."""
    # dismissed_keys folds legacy dismissals in before the restore is recorded,
    # otherwise the migration would re-dismiss this finding after the fact.
    state = dismissed_keys(project_dir)
    log = writer or ActionLogWriter(project_dir)
    log.emit_many([undismiss_event(e) for e in _undismiss_targets(project_dir, state, finding)])


def dismissed_keys(project_dir: Path) -> DismissedKeys:
    """Return the project's net dismissed state.

    Reads ``actions.jsonl`` directly and replays ``FINDING_DISMISSED`` /
    ``FINDING_UNDISMISSED`` in order (``fold_dismissals``), so the result
    reflects user intent regardless of whether any individual run has been
    projected into SQL. The actions log is the source of truth -- the SQL
    projection is a downstream view that folds the same log with the same
    function.

    The previous implementation read ``WHERE verdict = 'dismissed'`` from
    each run's ``findings`` table. That broke for older runs that don't
    have an ``events.jsonl``: the findings table stayed empty, so SQL had
    nothing to surface, so rescore saw an empty dismissed set, so the
    score never moved after a dismiss.
    """
    if not project_dir.is_dir():
        return EMPTY_DISMISSED

    # Pure-legacy projects (dismissed.json, no actions.jsonl, no events.jsonl)
    # have nothing in the action log until this fold runs. Trigger it at the
    # read seam so the very first score/list after upgrade reflects the user's
    # existing dismissals instead of an empty set. Then upgrade line-keyed
    # entries to fingerprints, once, so they survive the next refactor.
    migrate_if_needed(project_dir)
    backfill_if_needed(project_dir)
    return fold_dismissals(read_action_events(project_dir))


def load_dismissed(
    project_dir: Path,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict]:
    """List dismissed findings as dicts (shape matches /api/findings/dismissed response).

    The listing needs ``dismissed_keys`` and lives in ``_dismissed_listing``;
    the import is deferred so this module stays its import root.
    """
    from quodeq.services._dismissed_listing import load_dismissed as listing  # noqa: PLC0415

    return listing(project_dir, offset=offset, limit=limit)


def restore_all_findings(project_dir: Path, *, writer: ActionLog | None = None) -> int:
    """Append FindingUndismissed events for all currently-dismissed findings.

    Returns the count of restored items.
    """
    state = dismissed_keys(project_dir)
    if not state:
        return 0
    log = writer or ActionLogWriter(project_dir)
    log.emit_many([undismiss_event(entry) for entry in state.entries])
    return len(state)


def recount_totals(
    violations: list[Finding],
    compliance_count: int | None = None,
    old_totals: Totals | None = None,
    files_read: int | None = None,
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
        violations_per100_files=violations_per_100_files(len(violations), files_read),
    )


def filter_dismissed_from_dimensions(
    dimensions: list, project_dir: Path,
) -> list:
    """Return a new list of DimensionResult with dismissed findings removed.

    Recalculates totals for any dimension whose violations were filtered.
    Leaves compliance, principles, overall_score, overall_grade unchanged.
    """
    keys = dismissed_keys(project_dir)
    rules = load_suppression_rules(project_dir)
    if not keys and not rules:
        return dimensions
    result = []
    for dim in dimensions:
        filtered = [
            v for v in dim.violations
            if not is_dismissed(keys, req=v.req, principle=v.practice_id,
                                file=v.file, line=v.line, snippet=v.snippet, rules=rules)
        ]
        if len(filtered) == len(dim.violations):
            result.append(dim)
        else:
            result.append(replace(
                dim,
                violations=filtered,
                totals=recount_totals(filtered, old_totals=dim.totals, files_read=dim.files_read),
            ))
    return result
