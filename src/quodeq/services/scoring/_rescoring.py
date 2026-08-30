"""Accumulated-rescore machinery for the scoring reader.

Applies the project-wide dismiss/delete rescore to accumulated payloads,
tracking coverage so a partial rescore is served but never persisted
(the 2026-07-29 cache-poison incident). Moved out of the package
``__init__`` in the ScoringReader decomposition; the facade re-exports
every name, so callers and patch targets are unchanged.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.core.scoring.params import DEFAULT_PARAMS, ScoringParams
from quodeq.services.dashboard import _make_run_dimension_fetcher
from quodeq.services.deleted import deleted_keys
from quodeq.services.dismissed import dismissed_keys
from quodeq.services.ports import load_suppression_rules
from quodeq.services.rescore import rescore_dimensions
from quodeq.services.scoring._deps import ScoringDeps, _NO_DEPS
from quodeq.services.scoring._summary import recompute_summary
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


def _rescore_runs_by_dimension(
    dims: list[dict], reports_root: Path, project: str,
    dismissed: set[tuple], deleted: set[tuple] | None = None,
    params: ScoringParams = DEFAULT_PARAMS,
) -> dict[str, dict]:
    """Rescore each unique run and return a map of dim_key -> rescored dict."""
    validate_path_segment(project)
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
            validate_path_segment(run_id)
            run_dims = fetcher(run_id)
            # Grouped per run, so this run's own directory is the evidence
            # basis for every dimension sourced from it.
            result = rescore_dimensions(
                run_dims, dismissed, deleted, params=params,
                run_dir=reports_root / project / run_id,
                rules=load_suppression_rules(reports_root / project))
            seen_runs[run_id] = {
                (rd.get("dimension") or "").lower(): rd
                for rd in result.get("dimensions", [])
            }
        rd = seen_runs[run_id].get(dim_key)
        if rd:
            rescored_by_dim[dim_key] = rd
    return rescored_by_dim


def _dims_expecting_rescore(dims: list[dict]) -> set[str]:
    """Dimension keys that carry a source run and therefore expect a rescore."""
    return {
        (d.get("dimension") or "").lower()
        for d in dims
        if (d.get("dimension") or "") and (d.get("fromRunId") or d.get("runId"))
    }


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


def _rescore_accumulated_with_coverage(
    accumulated: dict[str, Any],
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    deps: ScoringDeps | None = None,
) -> tuple[dict[str, Any], bool]:
    """Apply rescore to an accumulated response dict (in-place compatible shape).

    Filters dismissed violations from each dimension, recalculates scores,
    and recomputes the summary.

    Returns ``(payload, complete)``. ``complete`` is False when at least one
    dimension that has a source run got no rescored entry back (e.g. the run
    read returned a partial dim set), in which case the missing dimensions
    keep their raw baked scores and the payload MUST NOT be persisted: its
    version hash cannot tell it apart from a fully rescored one.
    """
    d = deps or _NO_DEPS
    project_dir = reports_root / project
    dismissed = (d.dismissed_keys or dismissed_keys)(project_dir)
    deleted = (d.deleted_keys or deleted_keys)(project_dir)
    if (not dismissed and not deleted) or not accumulated:
        return accumulated, True

    dims = accumulated.get("dimensions", [])
    if not dims:
        return accumulated, True

    rescored_by_dim = (d.rescore_runs_by_dimension or _rescore_runs_by_dimension)(
        dims, reports_root, project, dismissed, deleted, params=params,
    )
    missing = _dims_expecting_rescore(dims) - set(rescored_by_dim)
    if missing:
        _logger.warning(
            "accumulated rescore for %s covered %d of %d dimensions (missing: %s); "
            "serving the partial result without caching it",
            project, len(rescored_by_dim), len(dims), sorted(missing),
        )
    new_dims = _merge_rescored_dims(dims, rescored_by_dim)

    new_summary = (d.recompute_summary or recompute_summary)(
        new_dims, accumulated.get("summary", {}), params=params,
    )
    return {**accumulated, "dimensions": new_dims, "summary": new_summary}, not missing


def _rescore_accumulated_response(
    accumulated: dict[str, Any],
    reports_root: Path,
    project: str,
    params: ScoringParams = DEFAULT_PARAMS,
    deps: ScoringDeps | None = None,
) -> dict[str, Any]:
    """`_rescore_accumulated_with_coverage` for callers that don't persist."""
    payload, _complete = _rescore_accumulated_with_coverage(
        accumulated, reports_root, project, params=params, deps=deps,
    )
    return payload


