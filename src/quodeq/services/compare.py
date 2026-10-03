"""Slim per-project score summaries for the Compare screen.

The Compare tab needs, for every project at once, the accumulated scores at
all three levels (overall / dimension / principle) plus severity totals and
the score trend, but never the findings themselves. A project's score-cache
rows carry exactly that, with dismissals applied, so a summary is built from
``ProjectRows`` without reading a single evaluation report: the only reads
are the run listing and the project's suppressions. The whole fleet is
served by one request (``build_fleet_compare``) over one score-cache
connection.

A parent project folds its children's runs and suppressions into its
scores; those live outside the project's rows, so parents keep the full
``get_project_scores`` path. A dimension of an untouched run reports
``quarantinedCount`` 0: the count lives only in the evaluation report.
"""
from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services._fs_metadata import local_repo_root
from quodeq.services.grade_formula import is_custom
from quodeq.services.wiring import count_commits_since, find_children, score_cache_session
from quodeq.services.scoring import ProjectRows, get_project_scores

#: What a project's summary build may raise and the fleet reports per project.
COMPARE_ERRORS = (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError)

_GIT_TIMEOUT_S = 5

# The finding arrays are the multi-MB part of a dimension payload. Everything
# else (scores, grades, principles, totals, coverage counts, staleness) is
# small and passes through untouched so this stays shape-compatible with the
# full /scores payload.
_HEAVY_DIMENSION_KEYS = ("violations", "compliance")

# Trend entries are already slim except dimensionDetails, which carries
# per-dimension grade/delta strings Compare doesn't need.
_TREND_DETAIL_KEYS = ("dimension", "score")
_DIMENSION_DETAILS_KEY = "dimensionDetails"


def _slim_dimension(dim: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in dim.items() if k not in _HEAVY_DIMENSION_KEYS}


def _slim_trend_entry(entry: dict[str, Any]) -> dict[str, Any]:
    slim = {k: v for k, v in entry.items() if k != _DIMENSION_DETAILS_KEY}
    slim[_DIMENSION_DETAILS_KEY] = [
        {k: d.get(k) for k in _TREND_DETAIL_KEYS}
        for d in entry.get(_DIMENSION_DETAILS_KEY) or []
    ]
    return slim


def _commits_since(repo_root: Path | None, since_iso: str | None) -> int | None:
    """Commits in the analyzed repo since *since_iso*, or None when unknowable.

    This is the real staleness signal: a grade measured before the code
    moved is provisional no matter how recent the run is. Runs don't record
    a commit hash (the cache key deliberately excludes it), so the count is
    time-based against the last scored run's date. Fails open to None on
    any git trouble -- a missing repo, no git, a timeout (the adapter owns
    the subprocess call).
    """
    if repo_root is None or not since_iso:
        return None
    return count_commits_since(repo_root, since_iso, timeout_s=_GIT_TIMEOUT_S)


def _summary(
    reports_root: Path, project: str, accumulated: dict[str, Any], trend: list[dict], runs: list[dict],
) -> dict[str, Any]:
    slim_trend = [_slim_trend_entry(e) for e in trend]
    # Newest scored run's date (trend is newest-first and excludes cancelled
    # and failed runs): the moment the current grade was measured.
    since_iso = slim_trend[0].get("dateISO") if slim_trend else None
    return {
        "project": project,
        "summary": accumulated.get("summary") or {},
        "dimensions": [_slim_dimension(d) for d in accumulated.get("dimensions") or []],
        "trend": slim_trend,
        "runsCount": len(runs),
        "lastRun": runs[0] if runs else None,
        "commitsSinceLastRun": _commits_since(local_repo_root(reports_root, project), since_iso),
        "scoring": {"customFormula": is_custom()},
    }


def _parent_summary(reports_root: Path, project: str) -> dict[str, Any]:
    scores = get_project_scores(reports_root, project) or {}
    return _summary(
        reports_root, project, scores.get("accumulated") or {}, scores.get("trend") or [],
        scores.get("availableRuns") or [],
    )


def build_compare_summary(reports_root: Path, project: str) -> dict[str, Any] | None:
    """Return the slim scores payload for one project, or None if unknown.

    Built from the project's score-cache rows, which carry the dismiss/delete
    rescore. Compare must never read the raw ``/accumulated`` payload (it is
    dismissal-blind).
    """
    if not (reports_root / project).exists():
        return None
    if find_children(reports_root, project):
        return _parent_summary(reports_root, project)
    rows = ProjectRows.load(reports_root, project)
    runs = [{"runId": r.run_id, "dateLabel": r.date_label, "status": r.status} for r in rows.runs]
    if not runs:
        return _summary(reports_root, project, {}, [], [])
    return _summary(reports_root, project, rows.accumulated(), rows.trend(), runs)


def build_fleet_compare(
    reports_root: Path, projects: list[str], *, log: LogSink = NULL_LOG,
) -> dict[str, Any]:
    """The summaries of *projects*, in order, plus the failures by project name.

    One score-cache connection serves the whole fleet. A project that is
    unknown or whose build fails lands in ``errors`` and does not block the
    others; a name listed twice is built once.
    """
    summaries: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    with score_cache_session():
        for project in dict.fromkeys(projects):
            try:
                summary = build_compare_summary(reports_root, project)
            except COMPARE_ERRORS as exc:
                log.error(f"Compare summary failed for project {project}: {exc!r}")
                errors[project] = "Failed to load compare summary"
                continue
            if summary is None:
                errors[project] = "Project not found"
            else:
                summaries.append(summary)
    return {"summaries": summaries, "errors": errors}
