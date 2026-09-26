"""Accumulated-trend builder for the dashboard module."""
from __future__ import annotations

from typing import Callable, TypedDict

from quodeq.core.run.state import RunState
from quodeq.core.scoring.internals import score_to_grade_label
from quodeq.core.scoring.params import ScoringParams
from quodeq.core.scoring.report_grades import most_frequent_grade, parse_numeric_score
from quodeq.core.types import DimensionResult
from quodeq.core.types.severity import Severity
from quodeq.data.fs.report_parser.runs import RunInfo
from quodeq.services.accumulated import numeric_average


class RunInfoPayload(TypedDict):
    """A run's identity on the wire: id plus its ISO and display dates.

    Every response that names a run (``availableRuns``, ``selectedRun``,
    ``trend``) carries these three keys, in this order.
    """
    runId: str
    dateISO: str | None
    dateLabel: str


def run_info_payload(info: RunInfo) -> RunInfoPayload:
    """*info*'s ``runId``, ``dateISO`` and ``dateLabel`` wire keys."""
    return {
        "runId": info.run_id,
        "dateISO": info.date_iso,
        "dateLabel": info.date_label,
    }


class DimensionDetail(TypedDict):
    """One dimension's score/grade/delta within a single run's trend entry.

    Shape only -- this IS the frozen HTTP body (``trend[].dimensionDetails``);
    the TypedDict documents it without changing what gets built or returned.
    """
    dimension: str
    score: float | None
    grade: str | None
    delta: float | None
    violations: int
    majors: int
    openTypes: int


class TrendEntry(TypedDict):
    """One run's accumulated-trend row, in the shape the dashboard HTTP
    response and the UI's history chart consume.

    Shape only -- this IS the frozen HTTP body (``trend``); the TypedDict
    documents it without changing what gets built or returned.
    """
    runId: str
    dateISO: str | None
    dateLabel: str
    status: str
    dimensionsCount: int
    dimensions: list[str]
    dimensionDetails: list[DimensionDetail]
    accumulatedDimensionsCount: int
    runNumericAverage: float | None
    runOverallGrade: str | None
    numericAverage: float | None
    overallGrade: str | None
    violations: int
    majors: int
    openTypes: int


def _build_dimension_details(
    run_dims: list[DimensionResult],
    prev_by_dim: dict[str, DimensionResult],
) -> list[DimensionDetail]:
    """Build per-dimension detail dicts with score deltas for a single run."""
    details: list[DimensionDetail] = []
    for dim in sorted(run_dims, key=lambda d: d.dimension or ""):
        if not dim.dimension:
            continue
        prev = prev_by_dim.get(dim.dimension)
        score = parse_numeric_score(dim.overall_score) if dim.overall_score else None
        prev_score = parse_numeric_score(prev.overall_score) if prev and prev.overall_score else None
        delta = round(score - prev_score, 2) if score is not None and prev_score is not None else None
        details.append({
            "dimension": dim.dimension,
            "score": score,
            "grade": dim.overall_grade,
            "delta": delta,
            **_dimension_counts(dim),
        })
    return details


_BLOCKING = frozenset({Severity.CRITICAL, Severity.MAJOR})
_COUNT_KEYS = ("violations", "majors", "openTypes")


def _dimension_counts(dim: DimensionResult) -> dict[str, int]:
    """The counts a user can watch converge: active violations, majors
    (critical + major) and open requirement types (distinct ``req``)."""
    active = list(dim.violations or [])
    return {
        "violations": len(active),
        "majors": sum(1 for f in active if f.severity in _BLOCKING),
        "openTypes": len({f.req for f in active if f.req}),
    }


def _run_counts(details: list[DimensionDetail]) -> dict[str, int]:
    """Sums over the run's dimensions; open types are summed per dimension,
    since a requirement code belongs to one dimension."""
    return {key: sum(int(d.get(key) or 0) for d in details) for key in _COUNT_KEYS}


def _build_trend_entry(
    item: RunInfo,
    run_dims: list[DimensionResult],
    acc_by_dim: dict[str, DimensionResult],
    prev_by_dim: dict[str, DimensionResult],
    params: ScoringParams,
) -> TrendEntry:
    """Build one run's trend row. *acc_by_dim* must already include this
    run's dims (the accumulation happens in the caller before this is
    called); *prev_by_dim* is updated in place with this run's dims for the
    next (newer) iteration to diff against."""
    acc_dims = list(acc_by_dim.values())
    acc_grades = [d.overall_grade for d in acc_dims if d.overall_grade]
    acc_avg = numeric_average(acc_dims, params)
    run_avg = numeric_average(run_dims, params)
    run_grades = [d.overall_grade for d in run_dims if d.overall_grade]
    run_dim_names = sorted(d.dimension for d in run_dims if d.dimension)
    dim_details = _build_dimension_details(run_dims, prev_by_dim)
    for dim in run_dims:
        if dim.dimension:
            prev_by_dim[dim.dimension] = dim
    return {
        **run_info_payload(item),
        # Surface the run's RunState so the History row can render
        # "running" instead of a misleading completion time while the
        # evaluation is still RunState.RUNNING (some dims have scored,
        # others haven't). Serializes as its wire value (e.g. "running"),
        # see quodeq.core.run.state.RunState.
        "status": item.status,
        "dimensionsCount": len(run_dim_names),
        "dimensions": run_dim_names,
        "dimensionDetails": dim_details,
        "accumulatedDimensionsCount": len(acc_by_dim),
        "runNumericAverage": run_avg,
        "runOverallGrade": (
            score_to_grade_label(run_avg, params=params) if run_avg is not None
            else (most_frequent_grade(run_grades) if run_grades else None)
        ),
        "numericAverage": acc_avg,
        "overallGrade": (
            score_to_grade_label(acc_avg, params=params) if acc_avg is not None
            else (most_frequent_grade(acc_grades) if acc_grades else None)
        ),
        **_run_counts(dim_details),
    }


def build_accumulated_trend(
    runs: list[RunInfo],
    get_run_dimensions: Callable[[str], list[DimensionResult]],
    params: ScoringParams | None = None,
) -> list[TrendEntry]:
    """Build trend using accumulated scores across all runs (oldest to newest).

    When *params* is None, the saved grade-formula params are loaded so the
    per-run and accumulated grade labels honour the user's custom formula.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    trend: list[TrendEntry] = []
    acc_by_dim: dict[str, DimensionResult] = {}
    prev_by_dim: dict[str, DimensionResult] = {}
    for item in reversed(runs):  # oldest -> newest
        run_dims = get_run_dimensions(item.run_id)
        for dim in run_dims:
            if dim.dimension:
                acc_by_dim[dim.dimension] = dim
        if not run_dims:
            continue
        trend.append(_build_trend_entry(item, run_dims, acc_by_dim, prev_by_dim, params))
    trend.reverse()
    return trend


def build_partial_run_entries(
    runs: list[RunInfo],
    get_run_dimensions: Callable[[str], list[DimensionResult]],
    params: ScoringParams | None = None,
) -> list[TrendEntry]:
    """Own-score rows for the cancelled runs in *runs* that scored a dimension.

    Kept apart from the trend on purpose: a cancelled run is not a history
    point, so its accumulated fields and deltas are None and nothing that
    reads ``trend`` sees it. It is still an evaluation the user kept, and
    this is what lets History list it with its own grade. Same order as
    *runs*; cancelled runs with nothing scored are left out.
    """
    if params is None:
        from quodeq.services import grade_formula  # noqa: PLC0415
        params = grade_formula.load_params()
    entries: list[TrendEntry] = []
    for item in runs:
        if item.status is not RunState.CANCELLED:
            continue
        run_dims = get_run_dimensions(item.run_id)
        if not run_dims:
            continue
        entries.append(_build_trend_entry(item, run_dims, {}, {}, params))
    return entries
