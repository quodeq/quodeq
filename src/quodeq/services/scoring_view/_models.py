"""Frozen dataclasses returned by the resolver functions.

Every model here is immutable (``frozen=True``) and slot-only
(``slots=True``) — they're carrier objects, not behavior containers.
Behavior lives in the ``_resolution`` and ``_buckets`` modules and
returns instances of these.

Why centralised: when a downstream caller asks "what's the freshest
score for security and which run did it come from?", it gets a single
``DimResolution`` object with provenance baked in. No tuple-unpacking,
no separate dict for "where did this come from" — the data and its
origin travel together.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# DimResolution — one dimension's freshest trustworthy eval
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DimResolution:
    """Where a single dim's most recent trustworthy data came from.

    Returned by ``resolve_latest_per_dim`` for every dim that has a
    trustworthy eval file. The fields cover both the *value* (score,
    grade) and the *provenance* (which run, when, what state). UI cards
    use the value; UI badges use the provenance to explain to users why
    a card might not match the umbrella run they're viewing.
    """

    # Identity
    dim_id: str
    """The dimension key (e.g. 'security', 'usability')."""

    # Source eval file
    eval_path: Path
    """Absolute path to the ``evaluation/<dim>.json`` this score came from."""

    # Run provenance — fields the UI uses to render the "from run X" badge
    run_id: str
    run_state: Literal["complete", "in_progress", "cancelled"]
    """The run's status when this snapshot was taken. Used to drive the
    'partial' / 'running' chip on the dim card."""

    run_date_iso: str | None
    """When the run started (ISO-8601 string from ``RunInfo.date_iso``)."""

    # Quality / coverage signals — surfaced in tooltips
    files_read: int
    """Number of files the model actually inspected. ``> 0`` is part of
    the trustworthiness check; the raw value lets the UI show e.g.
    'analyzed 48 of 977 files' on the card."""

    # The user-facing score
    overall_score: str | None
    """The score string as written in the eval file (e.g. ``'8.4/10'``)."""

    overall_grade: str | None
    """The textual grade (e.g. ``'Good'``, ``'Exemplary'``)."""


# ---------------------------------------------------------------------------
# BucketView — one entry on the score-history chart
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BucketView:
    """One point on the score-history chart.

    Today: one bucket per day. Tomorrow could be per-week or per-commit.
    The shape stays constant; ``bucket_runs_by_day`` etc. are different
    factories for the same model.
    """

    bucket_label: str
    """Human-readable label for the bucket axis (e.g. ``'27 Apr 2026'``)."""

    bucket_iso: str
    """Sortable identifier for the bucket (e.g. ``'2026-04-27'``)."""

    # The run that drives this bucket's score — the latest *successful*
    # run within the bucket, per the model's "last valid run per bucket"
    # rule. Stored as a run_id so callers can fetch full data on demand.
    representative_run_id: str | None
    """Run that produced this bucket's score, or ``None`` if the bucket
    has no successful runs (in which case the chart should render the
    bar muted or skipped per UI policy)."""

    representative_run_date_iso: str | None

    # The score the chart displays for this bucket — computed from the
    # representative run's per-dim resolutions, averaged.
    overall_score: float | None
    """Numeric average of the bucket's per-dim scores. ``None`` for an
    empty bucket. The chart bar height reads this."""

    dim_count: int
    """How many dims contributed. ``< total_dims`` indicates partial
    coverage and the UI should mark the bar accordingly."""


# ---------------------------------------------------------------------------
# RunSummary — lightweight run metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RunSummary:
    """Minimal projection of a run for ranking + filter operations.

    A thinner shape than the full ``RunInfo`` from the parser layer —
    we don't need everything the parser exposes for predicate logic.
    """

    run_id: str
    date_iso: str | None
    status: str
    """One of the ``RUN_STATE_*`` constants from ``_states``."""

    exit_reason: str | None = None
    """Status-tag distinguishing budget-timeout from signal-cancel etc.
    Required to evaluate ``is_successful_run`` for ``cancelled`` runs."""


__all__ = ["DimResolution", "BucketView", "RunSummary"]
