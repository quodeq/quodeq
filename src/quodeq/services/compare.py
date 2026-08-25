"""Slim per-project score summaries for the Compare screen.

The Compare tab needs, for every project at once, the accumulated scores at
all three levels (overall / dimension / principle) plus severity totals and
the score trend -- but never the findings themselves. ``get_project_scores``
already produces all of that with dismissals applied server-side; this module
only strips the heavy finding arrays so a whole fleet's worth of payloads can
be fanned out one request per project without shipping multi-MB bodies.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from quodeq.services.scoring import get_project_scores

# The finding arrays are the multi-MB part of a dimension payload. Everything
# else (scores, grades, principles, totals, coverage counts, staleness) is
# small and passes through untouched so this stays shape-compatible with the
# full /scores payload.
_HEAVY_DIMENSION_KEYS = ("violations", "compliance")

# Trend entries are already slim except dimensionDetails, which carries
# per-dimension grade/delta strings Compare doesn't need.
_TREND_DETAIL_KEYS = ("dimension", "score")


def _slim_dimension(dim: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dim.items() if k not in _HEAVY_DIMENSION_KEYS}


def _slim_trend_entry(entry: dict[str, Any]) -> dict[str, Any]:
    slim = {k: v for k, v in entry.items() if k != "dimensionDetails"}
    slim["dimensionDetails"] = [
        {k: d.get(k) for k in _TREND_DETAIL_KEYS}
        for d in entry.get("dimensionDetails") or []
    ]
    return slim


def build_compare_summary(reports_root: Path, project: str) -> dict[str, Any] | None:
    """Return the slim scores payload for one project, or None if unknown.

    Scores come from ``get_project_scores`` -- the authoritative, cache-backed
    path that applies the dismiss/delete rescore. Compare must never read the
    raw ``/accumulated`` payload (it is dismissal-blind).
    """
    scores = get_project_scores(reports_root, project)
    if scores is None:
        return None
    accumulated = scores.get("accumulated") or {}
    runs = scores.get("availableRuns") or []
    return {
        "project": project,
        "summary": accumulated.get("summary") or {},
        "dimensions": [_slim_dimension(d) for d in accumulated.get("dimensions") or []],
        "trend": [_slim_trend_entry(e) for e in scores.get("trend") or []],
        "runsCount": len(runs),
        "lastRun": runs[0] if runs else None,
        "scoring": scores.get("scoring") or {},
    }
