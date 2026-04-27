"""Bucketing — group runs into chart-friendly time windows.

Today: per-day. Tomorrow could be per-week, per-commit, per-PR. The
shape of the output (``BucketView``) stays the same; only the grouping
function changes.

Why a separate module: the bucket factory is the only part of the
package that's *not* a per-dim concern. Keeping it isolated means
``resolve_latest_per_dim`` can be tested without bucket ceremony, and
``bucket_runs_by_day`` can be replaced wholesale when we want a
different granularity without touching the resolver.

This module is currently a stub — the chart will start consuming it in
a follow-up PR. Surface defined now so call sites have a target import.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from quodeq.data.fs.report_parser import RunInfo

from ._models import BucketView, RunSummary
from ._states import is_successful_run


# ---------------------------------------------------------------------------
# bucket_runs_by_day — group runs by their start date
# ---------------------------------------------------------------------------

def bucket_runs_by_day(runs: Iterable[RunInfo]) -> list[list[RunInfo]]:
    """Group *runs* into per-day lists, newest-bucket first.

    Each inner list is the runs that started on a given calendar day,
    in the same order as the input (typically newest-first per the
    parser's output). A run with no ``date_iso`` (parser couldn't
    extract a date — rare, usually pre-Plan-A runs) is dropped from
    bucketing entirely; those runs aren't useful on a temporal chart.

    Returns a list of buckets, not a dict, because callers want order
    (newest day first) for direct chart rendering — a dict would force
    an extra sort.
    """
    by_day: dict[str, list[RunInfo]] = defaultdict(list)
    for run in runs:
        if not run.date_iso:
            continue
        # ISO format starts with "YYYY-MM-DD" — the date portion is the
        # bucket key. We don't need to parse the full datetime here.
        day_key = run.date_iso[:10]
        by_day[day_key].append(run)

    # Sort buckets newest-day first; within a bucket, preserve input order
    # (which the parser guarantees is newest run first, see ``list_runs``).
    return [by_day[day] for day in sorted(by_day, reverse=True)]


# ---------------------------------------------------------------------------
# pick_representative_run — last successful run within a bucket
# ---------------------------------------------------------------------------

def pick_representative_run(
    bucket: list[RunInfo],
    *,
    exit_reason_lookup: "callable | None" = None,
) -> RunInfo | None:
    """Return the bucket's representative run, or ``None`` if none qualifies.

    The representative is the **latest successful** run in the bucket
    (per ``is_successful_run``). For buckets with no successful runs
    the chart should render an empty / muted bar — the bucket exists
    (the day had attempts) but no authoritative score is available.

    ``exit_reason_lookup`` is a callable ``(run_id) -> exit_reason | None``
    that the caller provides to read each run's ``status.json`` exit
    reason without forcing this module to import the full lifecycle
    layer. Callers in production pass a memoised reader; tests can
    pass ``lambda _: None`` when they don't need to distinguish
    cancellation reasons.
    """
    for run in bucket:  # newest first per ``bucket_runs_by_day``
        exit_reason = exit_reason_lookup(run.run_id) if exit_reason_lookup else None
        if is_successful_run(run.status, exit_reason):
            return run
    return None


__all__ = ["bucket_runs_by_day", "pick_representative_run"]
