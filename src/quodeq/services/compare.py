"""Slim per-project score summaries for the Compare screen.

The Compare tab needs, for every project at once, the accumulated scores at
all three levels (overall / dimension / principle) plus severity totals and
the score trend -- but never the findings themselves. ``get_project_scores``
already produces all of that with dismissals applied server-side; this module
only strips the heavy finding arrays so a whole fleet's worth of payloads can
be fanned out one request per project without shipping multi-MB bodies.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from quodeq.services._fs_metadata import _local_repo_root
from quodeq.services.scoring import get_project_scores

_GIT_TIMEOUT_S = 5

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


def _commits_since(repo_root: Path | None, since_iso: str | None) -> int | None:
    """Commits in the analyzed repo since *since_iso*, or None when unknowable.

    This is the real staleness signal: a grade measured before the code
    moved is provisional no matter how recent the run is. Runs don't record
    a commit hash (the cache key deliberately excludes it), so the count is
    time-based against the last scored run's date. Fails open to None on
    any git trouble -- a missing repo, no git, a timeout.
    """
    if repo_root is None or not since_iso:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-list", "--count", f"--since={since_iso}", "HEAD"],
            capture_output=True, encoding="utf-8", timeout=_GIT_TIMEOUT_S, check=False,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


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
    trend = [_slim_trend_entry(e) for e in scores.get("trend") or []]
    # Newest scored run's date (trend is newest-first and excludes cancelled
    # and failed runs) -- the moment the current grade was measured.
    since_iso = trend[0].get("dateISO") if trend else None
    return {
        "project": project,
        "summary": accumulated.get("summary") or {},
        "dimensions": [_slim_dimension(d) for d in accumulated.get("dimensions") or []],
        "trend": trend,
        "runsCount": len(runs),
        "lastRun": runs[0] if runs else None,
        "commitsSinceLastRun": _commits_since(_local_repo_root(reports_root, project), since_iso),
        "scoring": scores.get("scoring") or {},
    }
