"""Unified scoring module -- single source of truth for all score data.

Public API
----------
- ``get_scores_raw(reports_root, project, run_id)`` -- rescored data for one run
- ``get_project_scores(reports_root, project, as_of)`` -- full dashboard payload

All functions apply dismissals server-side and return the same data shapes
as the existing endpoints, so the frontend sees no schema change.
"""
from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from quodeq.core.types import DimensionResult, to_camel_dict
from quodeq.services.accumulated import compute_accumulated
from quodeq.services.dashboard import (
    DashboardCacheConfig,
    _make_run_dimension_fetcher,
)
from quodeq.services._dashboard_trend import build_accumulated_trend
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.ports import RunInfo, list_runs
from quodeq.services.rescore import _rescore_dimension, rescore_dimensions
from quodeq.services.scoring._rescore import rescore_run_raw
from quodeq.services.scoring._summary import recompute_summary


def _max_history_runs() -> int:
    """Read max history runs from env at call time for lazy configuration."""
    return int(os.environ.get("QUODEQ_MAX_HISTORY_RUNS", "100"))


def get_scores_raw(
    reports_root: Path, project: str, run_id: str,
) -> dict:
    """Return raw rescore dict for a single run (explorer detail compat)."""
    return rescore_run_raw(reports_root, project, run_id)


def _make_rescoring_fetcher(
    reports_root: Path, project: str,
) -> Callable[[str], list[DimensionResult]]:
    """Return a dimension fetcher that applies rescore (dismissals) to results.

    Wraps the standard cached fetcher so that build_accumulated_trend
    automatically gets rescored data.
    """
    base_fetcher = _make_run_dimension_fetcher(reports_root, project)
    dismissed = dismissed_keys(reports_root / project)
    if not dismissed:
        return base_fetcher

    def rescoring_fetcher(run_id: str) -> list[DimensionResult]:
        dims = base_fetcher(run_id)
        return [_rescore_dimension(d, dismissed) for d in dims]

    return rescoring_fetcher


def _rescore_runs_by_dimension(
    dims: list[dict], reports_root: Path, project: str, dismissed: set[tuple],
) -> dict[str, dict]:
    """Rescore each unique run and return a map of dim_key -> rescored dict."""
    dim_to_run: dict[str, str] = {}
    for d in dims:
        key = (d.get("dimension") or "").lower()
        rid = d.get("fromRunId") or d.get("runId")
        if key and rid:
            dim_to_run[key] = rid

    fetcher = _make_run_dimension_fetcher(reports_root, project)
    rescored_by_dim: dict[str, dict] = {}
    seen_runs: dict[str, dict[str, dict]] = {}
    for dim_key, run_id in dim_to_run.items():
        if run_id not in seen_runs:
            run_dims = fetcher(run_id)
            result = rescore_dimensions(run_dims, dismissed)
            seen_runs[run_id] = {
                (rd.get("dimension") or "").lower(): rd
                for rd in result.get("dimensions", [])
            }
        rd = seen_runs[run_id].get(dim_key)
        if rd:
            rescored_by_dim[dim_key] = rd
    return rescored_by_dim


def _merge_rescored_dims(dims: list[dict], rescored_by_dim: dict[str, dict]) -> list[dict]:
    """Merge rescored data into accumulated dimensions."""
    new_dims = []
    for d in dims:
        key = (d.get("dimension") or "").lower()
        rd = rescored_by_dim.get(key)
        if rd:
            new_dims.append({
                **d,
                "overallScore": rd.get("overallScore"),
                "overallGrade": rd.get("overallGrade"),
                "violations": rd.get("violations", d.get("violations", [])),
                "compliance": rd.get("compliance", d.get("compliance", [])),
                "principles": rd.get("principles", d.get("principles", [])),
                "totals": rd.get("totals", d.get("totals")),
            })
        else:
            new_dims.append(d)
    return new_dims


def _rescore_accumulated_response(
    accumulated: dict[str, Any],
    reports_root: Path,
    project: str,
) -> dict[str, Any]:
    """Apply rescore to an accumulated response dict (in-place compatible shape).

    Filters dismissed violations from each dimension, recalculates scores,
    and recomputes the summary.
    """
    dismissed = dismissed_keys(reports_root / project)
    if not dismissed or not accumulated:
        return accumulated

    dims = accumulated.get("dimensions", [])
    if not dims:
        return accumulated

    rescored_by_dim = _rescore_runs_by_dimension(dims, reports_root, project, dismissed)
    new_dims = _merge_rescored_dims(dims, rescored_by_dim)

    new_summary = recompute_summary(new_dims, accumulated.get("summary", {}))
    return {**accumulated, "dimensions": new_dims, "summary": new_summary}


def get_project_scores(
    reports_root: Path, project: str, as_of: str | None = None,
) -> dict[str, Any] | None:
    """Return the full scores payload for the dashboard.

    Returns a dict with:
      - accumulated: { dimensions, summary } (same shape as /accumulated endpoint)
      - trend: [{ runId, dateISO, ... }] (same shape as dashboard.trend)
      - availableRuns: [{ runId, dateLabel }]

    All scores have dismissals applied server-side.
    """
    if not (reports_root / project).exists():
        return None

    all_runs = list_runs(reports_root, project)
    if not all_runs:
        return {
            "accumulated": {"dimensions": [], "summary": {}},
            "trend": [],
            "availableRuns": [],
        }

    # Build accumulated using the existing service (returns full data with violations)
    accumulated = compute_accumulated(
        str(reports_root), project, as_of,
    )
    if accumulated is None:
        accumulated = {"dimensions": [], "summary": {}}

    # Apply rescore to accumulated dimensions
    accumulated = _rescore_accumulated_response(accumulated, reports_root, project)

    # Build trend using a rescoring fetcher (applies dismissals to each run).
    # Exclude cancelled/failed runs — their partial scores are misleading on
    # the history chart. They remain in availableRuns so the UI can show them
    # when the user asks for them explicitly.
    scoreable_runs = [r for r in all_runs if r.status not in ("cancelled", "failed")]
    history_runs = scoreable_runs[:_max_history_runs()]
    rescoring_fetcher = _make_rescoring_fetcher(reports_root, project)
    trend = build_accumulated_trend(history_runs, rescoring_fetcher)

    # Build available runs list
    available_runs = [
        {"runId": r.run_id, "dateLabel": r.date_label, "status": r.status}
        for r in all_runs
    ]

    return {
        "accumulated": accumulated,
        "trend": trend,
        "availableRuns": available_runs,
    }


__all__ = [
    "get_scores_raw",
    "get_project_scores",
]
