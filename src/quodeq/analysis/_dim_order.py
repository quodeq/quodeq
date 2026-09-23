"""Backlog-aware dimension order and per-dimension deadline slices.

The dim loop runs dimensions sequentially under one run-wide deadline, and
the cache only keeps files that finished. Truncation (deadline, failure
streak, cancel) therefore always lands on the last dimension in the list,
whose un-cached files come back on the next run -- so with a fixed order
one dimension's backlog compounds. In three consecutive self-evals
clean-architecture (always last) went 541 -> 676 -> 806 pending files while
every other dimension sat at ~190.

Two things break that loop: run the biggest backlog first, and give each
dimension its own slice of the remaining budget so truncation moves around
instead of always hitting the tail.

Reordering needs a backlog to rank by, so it only applies when every
dimension reports an ``incremental`` estimate: a clean scan, a diff run or
a cold cache queues everything anyway.
"""
from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

from quodeq.analysis.run_types import RunConfig
from quodeq.core.observability import NULL_LOG, LogSink

DimEstimates = dict[str, dict[str, Any]]

# Floor reserved for every dimension still to run. A fully-cached dimension
# does no AI work but still has to replay its cache entries, write evidence
# and score, so it needs more than the zero a pure proportional split would
# hand it once the backlog concentrates in one dimension.
_MIN_DIM_BUDGET_S = 60.0


def _backlog_counts(
    dimensions: Sequence[str], estimates: DimEstimates | None,
) -> dict[str, int] | None:
    """Pending file count per dim, or None when the estimates can't rank them.

    Returns None (keep the configured order) when the estimates are missing,
    don't cover every dimension, aren't all ``incremental``, or carry a
    count that isn't an int.
    """
    if not estimates:
        return None
    counts: dict[str, int] = {}
    for dim in dimensions:
        estimate = estimates.get(dim)
        if not isinstance(estimate, dict) or estimate.get("reason") != "incremental":
            return None
        count = estimate.get("count")
        if not isinstance(count, int) or isinstance(count, bool):
            return None
        counts[dim] = max(count, 0)  # a negative count would slice a deadline before now
    return counts


def order_by_backlog(
    dimensions: Sequence[str], estimates: DimEstimates | None, *, log: LogSink = NULL_LOG,
) -> tuple[list[str], dict[str, int] | None]:
    """Return (dimensions biggest-backlog-first, per-dim pending counts).

    ``sorted`` is stable, so ties keep the configured order. Falls back to
    the configured order with ``None`` counts whenever the estimates can't
    rank the dimensions.
    """
    counts = _backlog_counts(dimensions, estimates)
    if counts is None:
        return list(dimensions), None
    ordered = sorted(dimensions, key=lambda dim: -counts[dim])
    if ordered != list(dimensions):
        log.info(
            "[loop] dimension order by pending backlog: "
            + ", ".join(f"{dim} ({counts[dim]})" for dim in ordered),
        )
    return ordered, counts


def _dimension_deadline(
    now: float, run_deadline: float, counts: Sequence[int] | None, remaining_dims: int,
) -> float:
    """Deadline for the dimension about to run: its share of what is left.

    ``counts`` holds the pending file counts of the dimensions not yet run,
    the one about to run first; ``remaining_dims`` is how many are left.
    Unknown or all-zero counts fall back to equal shares.

    Only what is left after reserving ``_MIN_DIM_BUDGET_S`` for each of the
    *other* remaining dimensions is split proportionally, and the current
    dimension gets that floor even when its own share rounds to nothing.
    Without the reserve a single backlogged dimension takes the whole
    budget and the cheap cached ones behind it are skipped by the loop's
    deadline guard -- the run would produce one dimension's evidence
    instead of all of them. A budget too small to reserve a floor for
    everyone degrades to equal shares.

    The result is never later than the run deadline, and an already-spent
    budget returns the run deadline unchanged so the loop's own guard still
    stops the run.
    """
    budget = run_deadline - now
    if budget <= 0:
        return run_deadline
    dims = max(remaining_dims, 1)
    splittable = budget - _MIN_DIM_BUDGET_S * (dims - 1)
    if splittable <= 0:
        return min(now + budget / dims, run_deadline)
    total = sum(counts) if counts else 0
    share = counts[0] / total if counts and total > 0 else 1.0 / dims
    slice_s = max(splittable * share, min(_MIN_DIM_BUDGET_S, budget))
    return min(now + slice_s, run_deadline)


def apply_dim_deadline(
    config: RunConfig, remaining: Sequence[str], run_deadline: float | None,
    counts: Mapping[str, int] | None,
) -> None:
    """Narrow ``config.options.deadline_at`` to the next dimension's slice.

    ``remaining`` starts with the dimension about to run. A ``None`` run
    deadline means an unlimited budget: nothing to slice.
    """
    if run_deadline is None:
        return
    dim_counts = [counts.get(dim, 0) for dim in remaining] if counts else None
    config.options.deadline_at = _dimension_deadline(
        time.monotonic(), run_deadline, dim_counts, len(remaining),
    )
