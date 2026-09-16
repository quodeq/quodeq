"""Resolve a finding's snippet fingerprint and backfill legacy dismissals.

The dismiss identity is ``(req, file, fingerprint(req, snippet))`` (see
``core.finding_identity``). The client never computes the hash: the server
looks the snippet up in the run's own findings (SQL, then the legacy
``evaluation/*.json``), so the recorded fingerprint always matches what the
projection and the precedent reader hash from the same rows.

Entries written before fingerprints existed carry only ``(req, file, line)``.
``backfill_if_needed`` upgrades them once per project by appending a
fingerprinted ``FindingDismissed`` for every net-dismissed legacy entry whose
snippet can still be found; ``fold_dismissals`` lets the fingerprinted entry
supersede the line-keyed one. The log is append-only, so nothing is
rewritten: the projection's byte-offset staleness check keeps working and a
crash mid-backfill only leaves duplicate, idempotent events behind. Same
marker-file idempotency as ``data/migrations/dismissed_json_to_actions_log``.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.dismissals import DismissedEntry, DismissedKeys, fold_dismissals
from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.ports.actions_log import ActionLog
from quodeq.services._run_recency import run_dirs_newest_first
from quodeq.services._wiring import (
    MARKER_FILENAME,
    ActionLogWriter,
    read_action_events,
    read_finding_details,
    read_finding_details_from_json_eval,
    read_run_status_json,
)
from quodeq.shared.validation import resolve_child_dir

#: Sentinel written once the legacy entries of a project have been upgraded.
BACKFILL_MARKER = ".dismiss_fingerprints_backfilled"

# One lock for every project: the backfill runs once per project, off the
# request hot path, so per-path locks would only add state to reason about.
_backfill_lock = threading.Lock()


def _in_shared_results_clone(project_dir: Path) -> bool:
    """True for ``<clone>/evaluations/<project>`` inside a shared-results clone.

    Shared mirrors are read-only views refreshed by fetch + hard reset; a
    backfill written there would be discarded on the next refresh and the
    fingerprints must come from the publisher's own log instead.
    """
    root = project_dir.parent.parent
    return (root / MARKER_FILENAME).is_file() and (root / ".git").exists()


def _snippet_in_run(run_dir: Path, key: tuple[str, str, int]) -> str | None:
    """The snippet stored for the ``(req, file, line)`` *key* in *run_dir*, or None."""
    detail = read_finding_details(run_dir, {key}).get(key)
    if detail is None:
        detail = read_finding_details_from_json_eval(run_dir, {key}).get(key)
    if detail is None:
        return None
    return detail.get("snippet") or None


def _parse_iso(value: object) -> datetime | None:
    if isinstance(value, datetime):
        stamp = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            stamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def _started_at(run_dir: Path) -> datetime | None:
    status = read_run_status_json(run_dir)
    return _parse_iso(status.get("started_at")) if isinstance(status, dict) else None


def _candidate_runs(
    project_dir: Path, *, run_id: str | None, at: datetime | None,
) -> list[Path]:
    """Runs to search, most likely first.

    The named run comes first. When *at* (the dismissal's timestamp) is
    known, runs started after it are tried last: the user dismissed what a
    run of that time showed, and a later run may hold different code at the
    same line.

    *run_id* comes from the request body. It is matched against the
    project's real run directories (``resolve_child_dir``), never joined onto
    the path, so a traversal value names nothing and the walk proceeds
    without it.
    """
    ordered = run_dirs_newest_first(project_dir) if project_dir.is_dir() else []
    if at is not None:
        before = [r for r in ordered if (_started_at(r) or at) <= at]
        after = [r for r in ordered if r not in before]
        ordered = before + after
    resolved = resolve_child_dir(project_dir, run_id) if run_id and project_dir.is_dir() else None
    if resolved is not None:
        named = Path(resolved)
        ordered = [named] + [r for r in ordered if r != named]
    return ordered


def resolve_fingerprint(
    project_dir: Path, target: DismissedEntry, *,
    run_id: str | None = None, snippet: str | None = None,
) -> str | None:
    """The dismiss fingerprint of the finding *target* names by ``(req, file, line)``.

    The snippet is read from the project's own runs: the named run first,
    then newest first, with runs started after ``target.dismissed_at`` (when
    known) tried last. *snippet* is the client-supplied fallback for a finding
    no run holds any more. None when no snippet can be found: the dismissal
    then keeps its line as identity.
    """
    key = target.line_key
    for run_dir in _candidate_runs(project_dir, run_id=run_id, at=target.dismissed_at):
        found = _snippet_in_run(run_dir, key)
        if found:
            return snippet_fingerprint(target.req, found)
    return snippet_fingerprint(target.req, snippet)


def _upgrade_entry(entry: DismissedEntry, project_dir: Path) -> FindingDismissedEvent | None:
    fp = resolve_fingerprint(project_dir, entry)
    if fp is None:
        return None
    return FindingDismissedEvent(payload=FindingDismissed(
        req=entry.req, file=entry.file, line=entry.line,
        reason=entry.reason, fingerprint=fp,
    ))


def backfill_if_needed(
    project_dir: Path, *, writer: ActionLog | None = None, log: LogSink = NULL_LOG,
) -> int:
    """Upgrade a project's legacy line-keyed dismissals to fingerprints, once.

    Returns the number of entries upgraded. Entries whose finding no run
    holds any more (or that never had a snippet) stay line-keyed; the marker
    is written regardless so the walk over every run happens once. Shared
    mirrors are never written to.
    """
    marker = project_dir / BACKFILL_MARKER
    if marker.exists():
        return 0
    if not (project_dir / "actions.jsonl").is_file() or _in_shared_results_clone(project_dir):
        return 0

    with _backfill_lock:
        if marker.exists():
            return 0
        state: DismissedKeys = fold_dismissals(read_action_events(project_dir))
        pending = [e for e in state.entries if not e.fingerprint]
        count = 0
        if pending:
            sink = writer or ActionLogWriter(project_dir)
            for entry in pending:
                event = _upgrade_entry(entry, project_dir)
                if event is None:
                    continue
                sink.emit(event)
                count += 1
        # Mark last: a crash mid-backfill leaves the marker absent so the next
        # call retries; the events already appended are idempotent for the fold.
        try:
            marker.write_text("", encoding="utf-8")
        except OSError as exc:
            log.warning(f"Could not write backfill marker {marker}: {exc}")
        if pending:
            log.info(f"Fingerprinted {count} of {len(pending)} legacy dismissals in {project_dir}")
        return count
