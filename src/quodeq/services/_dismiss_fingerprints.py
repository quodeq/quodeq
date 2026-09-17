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
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.dismissals import DismissedEntry, DismissedKeys, fold_dismissals
from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.core.finding_identity import snippet_fingerprint
from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.data.ports.actions_log import ActionLog
from quodeq.services._run_recency import run_dirs_newest_first, run_started_at
from quodeq.services._wiring import (
    MARKER_FILENAME,
    ActionLogWriter,
    read_action_events,
    read_finding_details,
    read_finding_details_from_json_eval,
)
from quodeq.shared.validation import resolve_child_dir

#: Sentinel written once the legacy entries of a project have been upgraded.
BACKFILL_MARKER = ".dismiss_fingerprints_backfilled"

# Per-project single-flight, bounded. The backfill runs inside
# ``dismissed_keys()``, which is on the dashboard request path (GET
# /api/projects fans out over projects from a thread pool), so one lock for
# every project would serialize each project's first touch behind the slowest
# walk. ``_backfill_locks`` holds only the projects whose backfill is in
# flight: ``_single_flight`` evicts the entry once the project is done, marker
# written or skipped.
_locks_guard = threading.Lock()
_backfill_locks: dict[Path, threading.Lock] = {}


@contextmanager
def _single_flight(project_dir: Path) -> Iterator[None]:
    with _locks_guard:
        lock = _backfill_locks.setdefault(project_dir, threading.Lock())
    with lock:
        try:
            yield
        finally:
            with _locks_guard:
                if _backfill_locks.get(project_dir) is lock:
                    del _backfill_locks[project_dir]


def _in_shared_results_clone(project_dir: Path) -> bool:
    """True for ``<clone>/evaluations/<project>`` inside a shared-results clone.

    Shared mirrors are read-only views refreshed by fetch + hard reset; a
    backfill written there would be discarded on the next refresh and the
    fingerprints must come from the publisher's own log instead.
    """
    root = project_dir.parent.parent
    return (root / MARKER_FILENAME).is_file() and (root / ".git").exists()


LineKey = tuple[str, str, int]


def _snippets_in_run(run_dir: Path, keys: set[LineKey]) -> dict[LineKey, str]:
    """The snippets *run_dir* stores for those of the ``(req, file, line)`` *keys* it holds.

    One read of the findings table for the whole set; keys the table does
    not hold fall back to the legacy ``evaluation/*.json``. A key whose row
    has no snippet is absent.
    """
    details = read_finding_details(run_dir, keys)
    missing = keys.difference(details)
    if missing:
        details.update(read_finding_details_from_json_eval(run_dir, missing))
    return {key: detail["snippet"] for key, detail in details.items() if detail.get("snippet")}


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


def _resolve_fingerprints(
    project_dir: Path, targets: Iterable[DismissedEntry], *, run_id: str | None = None,
) -> dict[LineKey, str]:
    """The fingerprint of every target whose snippet one of the project's runs holds.

    Each run is read once, for every target still unresolved, in two waves:
    first the runs started before a target's dismissal (newest first), so the
    target matches what the user saw when they dismissed it, then the runs
    started after it, which may hold different code at the same line. A run
    with no recorded start counts as started before; a dismissal timestamp
    without a zone is read as UTC. The run *run_id* names is read first for
    every target. A blank stored snippet has no fingerprint and does not end
    its target's search. Targets no run holds are absent.

    *run_id* comes from the request body. It is matched against the
    project's real run directories (``resolve_child_dir``), never joined onto
    the path, so a traversal value names nothing and the walk proceeds
    without it.
    """
    if not project_dir.is_dir():
        return {}
    pending = {target.line_key: target for target in targets}
    dismissed_at = {key: _parse_iso(target.dismissed_at) for key, target in pending.items()}
    found: dict[LineKey, str] = {}
    started: dict[Path, datetime | None] = {}

    def started_before(run_dir: Path, at: datetime | None) -> bool:
        if at is None:
            return True
        if run_dir not in started:
            started[run_dir] = _parse_iso(run_started_at(run_dir))
        return (started[run_dir] or at) <= at

    def read(run_dir: Path, keys: set[LineKey]) -> None:
        for key, snippet in _snippets_in_run(run_dir, keys).items():
            fingerprint = snippet_fingerprint(pending[key].req, snippet)
            if fingerprint is not None:
                found[key] = fingerprint

    runs = run_dirs_newest_first(project_dir)
    resolved = resolve_child_dir(project_dir, run_id) if run_id else None
    if resolved is not None:
        named = Path(resolved)
        read(named, set(pending))
        runs = [run_dir for run_dir in runs if run_dir != named]
    for before in (True, False):
        for run_dir in runs:
            if len(found) == len(pending):
                return found
            keys = {
                key for key in pending
                if key not in found and started_before(run_dir, dismissed_at[key]) is before
            }
            if keys:
                read(run_dir, keys)
    return found


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
    found = _resolve_fingerprints(project_dir, [target], run_id=run_id)
    return found.get(target.line_key) or snippet_fingerprint(target.req, snippet)


def _upgraded(entry: DismissedEntry, fingerprint: str) -> FindingDismissedEvent:
    return FindingDismissedEvent(payload=FindingDismissed(
        req=entry.req, file=entry.file, line=entry.line,
        reason=entry.reason, fingerprint=fingerprint,
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

    with _single_flight(project_dir):
        if marker.exists():
            return 0
        state: DismissedKeys = fold_dismissals(read_action_events(project_dir))
        pending = [e for e in state.entries if not e.fingerprint]
        count = 0
        if pending:
            fingerprints = _resolve_fingerprints(project_dir, pending)
            events = [
                _upgraded(entry, fingerprint) for entry in pending
                if (fingerprint := fingerprints.get(entry.line_key))
            ]
            (writer or ActionLogWriter(project_dir)).emit_many(events)
            count = len(events)
        # Mark last: a crash mid-backfill leaves the marker absent so the next
        # call retries; the events already appended are idempotent for the fold.
        try:
            marker.write_text("", encoding="utf-8")
        except OSError as exc:
            log.warning(f"Could not write backfill marker {marker}: {exc}")
        if pending:
            log.info(f"Fingerprinted {count} of {len(pending)} legacy dismissals in {project_dir}")
        return count
