"""The accumulated view of one project built from score-cache rows.

``/scores`` used to compute its accumulated block twice: a walk over the
runs' grade tables picked the latest valid dimension per name, the winning
runs were read in full, and ``rescore_accumulated_with_coverage`` read them
again to apply the project's suppressions. The trend block, meanwhile, had
already rescored every run through the row-backed trend fetcher.

Here the accumulated block shares that fetcher. Its ``rows`` carry each
run's rescored score, grade, principles and files read, so the walk picks
winners and previous occurrences from them, and the only full read left is
the one that hydrates each winning run's finding lists. A winner keeps the
full read's findings minus what the suppressions exclude, with the row's
score, grade and principles over them; totals follow the rescore rule
(unchanged when nothing was excluded, recounted otherwise).

The as-of cut keeps ``compute_accumulated``'s semantics: *as_of* names a
run id, and a value that matches no run yields an empty view.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.scoring.params import ScoringParams
from quodeq.core.types import DimensionResult
from quodeq.services.accumulated import (
    AccumulatedResult,
    aggregate_severity_counts,
    build_accumulated_response,
    compute_accumulated_scores,
    compute_accumulated_trends,
    read_all_run_data,
)
from quodeq.services.dismissed import recount_totals
from quodeq.services.rescore import filter_excluded_violations
from quodeq.services.score_cache import run_rows
from quodeq.services.scoring._summary import recompute_summary
from quodeq.services.scoring_view import select_default_view_runs
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.services.wiring import RunInfo, load_suppression_rules

EMPTY_ACCUMULATED: dict[str, Any] = {"dimensions": [], "summary": {}}


@dataclass(frozen=True, slots=True)
class AccumulatedScope:
    """The project an accumulated view is built for and the rules it is graded under."""

    reports_root: Path
    project: str
    params: ScoringParams
    keys: SuppressionKeys


def runs_as_of(all_runs: list[RunInfo], as_of: str | None) -> list[RunInfo]:
    """*all_runs* (newest first) from the run *as_of* names; everything when None."""
    if not as_of:
        return all_runs
    idx = next((i for i, r in enumerate(all_runs) if r.run_id == as_of), None)
    return all_runs[idx:] if idx is not None else []


def _finish_winner(full: DimensionResult, row: DimensionResult, keys: SuppressionKeys) -> DimensionResult:
    """*full* minus the excluded findings, graded by *row*.

    Mirrors ``rescore_dimension``: a dimension no suppression touches is served
    as read; otherwise the row (which the rescore produced) supplies score,
    grade and principles, and the totals are recounted over what remains.
    """
    kept = filter_excluded_violations(full, keys)
    if len(kept) == len(full.violations):
        return full
    compliance_count = full.totals.compliance_count if full.totals else len(full.compliance)
    return replace(
        full, violations=kept,
        overall_score=row.overall_score, overall_grade=row.overall_grade, principles=row.principles,
        totals=recount_totals(kept, compliance_count=compliance_count, files_read=full.files_read),
    )


def _hydrate_winners(
    latest_by_dim: dict[str, DimensionResult],
    fetch_full: Callable[[str], list[DimensionResult]],
    keys: SuppressionKeys,
) -> tuple[list[DimensionResult], bool]:
    """Winning row dimensions with their finding lists, one full read per winning run.

    The flag is False when a winning run's full read lacks a dimension its rows
    had; that dimension is served without findings and the payload must not be
    persisted (its version cannot tell it apart from a complete one).
    """
    names_by_run: dict[str, list[str]] = {}
    for name, row in latest_by_dim.items():
        names_by_run.setdefault(row.from_run_id or "", []).append(name)
    finished: dict[str, DimensionResult] = {}
    complete = True
    for run_id, names in names_by_run.items():
        full_by_name: dict[str, DimensionResult] = {}
        for dim in fetch_full(run_id) if run_id else []:
            full_by_name.setdefault(dim.dimension, dim)
        for name in names:
            row = latest_by_dim[name]
            full = full_by_name.get(name)
            if full is None:
                complete = False
                finished[name] = row
                continue
            finished[name] = replace(
                _finish_winner(full, row, keys),
                from_run_id=row.from_run_id, from_date_iso=row.from_date_iso,
                from_date_label=row.from_date_label,
            )
    return [finished[name] for name in latest_by_dim], complete


def build_accumulated_from_rows(
    scope: AccumulatedScope, runs: list[RunInfo],
    fetcher: Callable[[str], list[DimensionResult]],
    fetch_full: Callable[[str], list[DimensionResult]],
) -> tuple[dict[str, Any], bool]:
    """The accumulated payload for *runs* (already cut at as-of) and whether it is complete.

    *fetcher* is the project's trend fetcher; its rows drive the walk.
    *fetch_full* reads a winning run's findings. ``scope.keys`` are the
    project's dismissals and deletions; the pattern rules are read here.
    """
    eligible = select_default_view_runs(runs)
    if not eligible:
        return EMPTY_ACCUMULATED, True
    reports_root, project, params = scope.reports_root, scope.project, scope.params
    latest_by_dim, prev_occurrence, prev_run_latest = read_all_run_data(
        reports_root, project, eligible, get_run_data=run_rows(fetcher),
    )
    run_keys = replace(scope.keys, rules=load_suppression_rules(reports_root / project))
    all_dims, complete = _hydrate_winners(latest_by_dim, fetch_full, run_keys)
    result = AccumulatedResult(
        all_dims, compute_accumulated_trends(all_dims, prev_occurrence),
        aggregate_severity_counts(all_dims),
        *compute_accumulated_scores(all_dims, prev_run_latest, params),
    )
    response = build_accumulated_response(project, result, params)
    response["summary"] = recompute_summary(response["dimensions"], response["summary"], params=params)
    return response, complete
