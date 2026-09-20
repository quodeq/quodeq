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
    read_finding_details,
    read_finding_details_from_json_eval,
)
from quodeq.services.dismissed import dismissed_keys


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


def _collect_dismissed_details(
    project_dir: Path, keys: set[DismissKey],
) -> dict[DismissKey, dict]:
    """Look up finding detail for every dismissed key, newest run first.

    Each run is asked only for the keys still missing, so older runs do less
    work and the walk stops once every key has detail. Newest-first plus
    ``setdefault`` in the enrichers makes the merge deterministic: the detail
    shown is always the most recent run's -- for a fingerprinted entry that
    is the finding's current location, whatever line it has moved to.
    """
    details: dict[DismissKey, dict] = {}
    for run_dir in run_dirs_newest_first(project_dir):
        missing = keys.difference(details)
        if not missing:
            break
        _enrich_from_sql(run_dir, missing, details)
        missing = keys.difference(details)
        if missing:
            _enrich_from_json_eval(run_dir, missing, details)
    return details


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

    Only the entries on the requested page are looked up in the runs; the
    items are one-to-one with the entries, so paging the entries first gives
    the same page as paging the full listing would.
    """
    if not project_dir.is_dir():
        return []
    state = dismissed_keys(project_dir)
    if not state:
        return []
    page = _page(state.entries, offset, limit)
    if not page:
        return []
    details = _collect_dismissed_details(project_dir, {e.key for e in page})
    return _dismissed_items(page, details)


def _page(
    entries: tuple[DismissedEntry, ...], offset: int, limit: int | None,
) -> tuple[DismissedEntry, ...]:
    """The slice of *entries* a page names; all of them when no page is asked for."""
    if offset <= 0 and limit is None:
        return entries
    start = max(0, offset)
    end = start + limit if limit is not None and limit >= 0 else None
    return entries[start:end]
