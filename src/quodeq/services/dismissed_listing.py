"""The Dismissed tab listing: finding detail for every net-dismissed entry.

``actions.jsonl`` is the source of truth for *which* findings are dismissed
(``services.dismissed.dismissed_keys``). The original finding detail is
looked up from each run's SQL ``findings`` table when the run has been
projected, with a JSON-eval-file fallback for legacy runs that never
produced an ``events.jsonl``. Without that fallback, the Dismissed tab was
permanently empty for any project whose runs pre-date the event-log scoring
engine -- even though the rescore + dismissed-set math always worked because
both go through ``actions.jsonl``.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.dismissals import DismissedEntry
from quodeq.core.finding_identity import DismissKey
from quodeq.services._run_recency import run_dirs_newest_first
from quodeq.services.wiring import (
    ACTIONS_LOG_FILENAME,
    read_finding_details,
    read_finding_details_from_json_eval,
)
from quodeq.services.dismissed import dismissed_keys
from quodeq.shared.stamp_memo import StampCache, file_stamp, memoized_by_stamp

# The resolved detail of every dismissed entry, per project, reused while the
# actions log and the run list are unchanged. An entry whose finding no run
# holds any more costs a walk over every run (measured at 5.9 s for 382
# runs); without this memo the Dismissed tab paid it on every open.
_DETAILS = StampCache(max_entries=64, name="dismissed.details")


def _enrich_from_sql(run_dir: Path, keys: set[DismissKey], out: dict[DismissKey, dict]) -> None:
    """Add finding detail from a run's SQL findings table for any dismissed key not yet enriched.

    Modern runs (those with an ``events.jsonl`` projected into ``findings``)
    expose the full Judgment row here. The lookup and its schema knowledge
    live in the data layer (``findings_queries``); ``setdefault`` keeps the
    first hit, and the caller walks runs newest-first, so the newest wins.
    """
    for key, detail in read_finding_details(run_dir, keys).items():
        out.setdefault(key, detail)


def _enrich_from_json_eval(
    run_dir: Path, keys: set[DismissKey], out: dict[DismissKey, dict],
) -> None:
    """Add finding detail from a run's ``evaluation/<dim>.json`` files.

    Used for legacy runs that pre-date the event-log scoring engine and so
    never produced a SQL ``findings`` table. The JSON files carry every
    field the Dismissed tab needs (principle, severity, title, reason,
    snippet, context, req_refs); ``dimension`` comes from the filename so
    the entry stays linked to its standard for the restore/delete flows.
    The walk and field mapping live in the data layer beside the SQL twin;
    ``setdefault`` keeps the first hit, so the newest run wins (see caller).
    """
    for key, detail in read_finding_details_from_json_eval(run_dir, keys).items():
        out.setdefault(key, detail)


def _recorded_run_dirs(
    entries: tuple[DismissedEntry, ...], runs: list[Path],
) -> list[Path]:
    """The run dirs the entries were dismissed from, newest first, each once.

    Only runs the recency walk knows are returned: the recorded id is a plain
    directory name at best and a stale one at worst, so it is matched against
    the listing rather than joined onto the project path.
    """
    by_name = {run_dir.name: run_dir for run_dir in runs}
    seen: set[Path] = set()
    out: list[Path] = []
    for entry in entries:
        run_dir = by_name.get(entry.run_id or "")
        if run_dir is None or run_dir in seen:
            continue
        seen.add(run_dir)
        out.append(run_dir)
    return out


def _collect_dismissed_details(
    project_dir: Path, entries: tuple[DismissedEntry, ...],
) -> dict[DismissKey, dict]:
    """Look up finding detail for every dismissed entry.

    The newest run is asked first: a finding still present there is shown at
    its current location, whatever line it has moved to. Then the runs the
    entries were dismissed from, for the keys still missing, so a finding
    that a later run no longer holds costs one lookup, not a walk. Then the
    remaining runs newest first, each asked only for what is still missing,
    until every key has detail. ``setdefault`` in the enrichers keeps the
    first hit, which makes the merge deterministic.
    """
    runs = run_dirs_newest_first(project_dir)
    keys = {entry.key for entry in entries}
    details: dict[DismissKey, dict] = {}
    if not runs or not keys:
        return details
    asked: set[Path] = set()

    def ask(run_dir: Path) -> None:
        missing = keys.difference(details)
        if not missing or run_dir in asked:
            return
        asked.add(run_dir)
        _enrich_from_sql(run_dir, missing, details)
        missing = keys.difference(details)
        if missing:
            _enrich_from_json_eval(run_dir, missing, details)

    ask(runs[0])
    for run_dir in _recorded_run_dirs(entries, runs):
        ask(run_dir)
    for run_dir in runs[1:]:
        if not keys.difference(details):
            break
        ask(run_dir)
    return details


def _listing_stamp(project_dir: Path) -> tuple:
    """What the resolved details depend on: the actions log and the run list."""
    runs = run_dirs_newest_first(project_dir)
    newest = runs[0].name if runs else ""
    return (file_stamp(project_dir / ACTIONS_LOG_FILENAME), newest, len(runs))


def _page_details(
    project_dir: Path, page: tuple[DismissedEntry, ...], offset: int, limit: int | None,
) -> dict[DismissKey, dict]:
    """The memoized detail map for the entries of one page of the listing.

    Keyed per page so a page asks the runs only about its own entries; the
    stamp drops the map when the actions log or the run list changes.
    """
    details = memoized_by_stamp(
        f"{project_dir}|{offset}|{limit}", _listing_stamp(project_dir),
        lambda: _collect_dismissed_details(project_dir, page),
        cache=_DETAILS,
    )
    return details if details is not None else {}


def _dismissed_items(
    entries: tuple[DismissedEntry, ...], details: dict[DismissKey, dict],
) -> list[dict]:
    """Build the response list, stubbing any entry whose detail wasn't found.

    ``req`` is always the entry's own: a no-req finding is recorded under
    its principle while its row carries an empty requirement, and the
    restore round-trip needs the recorded form. ``fingerprint`` rides along
    for the same reason.
    """
    items: list[dict] = []
    for entry in entries:
        match = details.get(entry.key)
        if match is not None:
            items.append({**match, "req": entry.req, "fingerprint": entry.fingerprint})
        else:
            # Couldn't find the original finding anywhere — surface a minimal
            # stub so the user can still see (and restore/delete) the entry.
            items.append({
                "req": entry.req, "file": entry.file, "line": entry.line,
                "fingerprint": entry.fingerprint,
                "dimension": "", "principle": "",
                "severity": "", "title": "", "reason": "",
                "snippet": "", "context": "", "scope": "",
                "endLine": 0, "reqRefs": [],
            })
    return items


def load_dismissed(
    project_dir: Path,
    *,
    offset: int = 0,
    limit: int | None = None,
) -> list[dict]:
    """List dismissed findings as dicts (shape matches /api/findings/dismissed response).

    Only the entries on the requested page are looked up in the runs, and
    the result is kept per page while nothing changes; the items are
    one-to-one with the entries, so paging the entries first gives the same
    page as paging the full listing would.
    """
    if not project_dir.is_dir():
        return []
    state = dismissed_keys(project_dir)
    if not state:
        return []
    page = _page(state.entries, offset, limit)
    if not page:
        return []
    return _dismissed_items(page, _page_details(project_dir, page, offset, limit))


def dismissed_item(project_dir: Path, req: str, file: str, line: int) -> dict | None:
    """The listing item for the entry recorded at ``(req, file, line)``, or None.

    What the Dismissed tab would show for a finding just dismissed, in the
    same shape as :func:`load_dismissed`, so a client can add it to the list
    it holds without fetching the list again. A fingerprinted entry is
    preferred over a line-keyed twin at the same place.
    """
    if not project_dir.is_dir():
        return None
    state = dismissed_keys(project_dir)
    entries = state.entries_at(req, file, line)
    if not entries:
        return None
    entry = next((e for e in entries if e.fingerprint), entries[0])
    (item,) = _dismissed_items((entry,), _collect_dismissed_details(project_dir, (entry,)))
    return item


def _page(
    entries: tuple[DismissedEntry, ...], offset: int, limit: int | None,
) -> tuple[DismissedEntry, ...]:
    """The slice of *entries* a page names; all of them when no page is asked for."""
    if offset <= 0 and limit is None:
        return entries
    start = max(0, offset)
    end = start + limit if limit is not None and limit >= 0 else None
    return entries[start:end]
