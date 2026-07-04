"""Rescore-after-mutation helpers, shared by API routes and assistant actions.

Moved out of ``api/routes_findings.py`` so the assistant's dismiss action can
reuse ``rescore_with_fallback`` without an assistant -> api layer import.
Behavior is unchanged: rescore the referenced run when possible, otherwise
kick a background projection so the mutation still lands in SQL. Distinct
from ``services/rescore.py``, which is the in-memory grade recompute engine.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)

# Per-project locks for background projection.  A module-level guard lock
# protects creation of per-project entries; after creation each project's Lock
# is accessed without the guard.
#
# Intentionally unbounded: one tiny Lock object per distinct project name that
# has ever triggered a background projection on this host.  In practice this
# mirrors the number of projects on disk, which is small and naturally bounded
# by real usage.  Contrast with _scored_jobs (bounded LRU) — scored jobs can
# accumulate many run-ids per project, so a size cap there is meaningful;
# here there is one entry per project, not per run.
_projection_locks: dict[str, threading.Lock] = {}
_projection_locks_guard = threading.Lock()


def _get_projection_lock(project: str) -> threading.Lock:
    """Return (and lazily create) the Lock for *project*."""
    with _projection_locks_guard:
        if project not in _projection_locks:
            _projection_locks[project] = threading.Lock()
        return _projection_locks[project]


def _resolve_project_dir(evaluations_dir: str, project: str) -> Path:
    """Jailed project-dir resolution; raises ValueError on escape attempts.

    The api layer's ``_project_dir`` does the same with a Flask ``abort``;
    this service-layer twin raises so non-HTTP callers can map the error
    themselves.
    """
    validate_path_segment(project)
    base = Path(evaluations_dir).resolve()
    resolved = (base / project).resolve()
    if not resolved.is_relative_to(base):
        raise ValueError("Invalid project path")
    return resolved


def _slim_scores(scores: dict[str, Any]) -> dict[str, Any]:
    """Drop violation/compliance arrays from the rescored payload.

    The UI's dismiss handlers (PrincipleDetail, FileDetail, FindingDetail)
    only need the per-dimension and per-principle ``score`` / ``grade``
    fields to update local state. Returning the full payload meant 300+ KB
    on large projects (quodeq: 322 KB → 543 B after slimming, a 600× cut),
    which was the bulk of the perceived dismiss latency: parse + transfer +
    re-render against violations the page already has from its initial fetch.
    """
    if not scores:
        return scores
    slim_dims = []
    for dim in scores.get("dimensions", []) or []:
        slim_principles = [
            {
                "principle": p.get("principle"),
                "score": p.get("score"),
                "grade": p.get("grade"),
            }
            for p in (dim.get("principles") or [])
        ]
        slim_dims.append({
            "dimension": dim.get("dimension"),
            "overallScore": dim.get("overallScore"),
            "overallGrade": dim.get("overallGrade"),
            "principles": slim_principles,
        })
    return {"dimensions": slim_dims, "summary": scores.get("summary", {})}


def _project_all_runs(project_dir: Path) -> None:
    """Trigger projection across every run dir of the project.

    Used as a safety net when the dismiss POST didn't carry a usable
    ``run_id`` (callers from the Violations / Map pages don't always have
    one in hand). Without this, the action lands in ``actions.jsonl`` but
    no run's SQL ``findings`` table is updated, so the dismissed-tab list
    — which reads ``WHERE verdict = 'dismissed'`` from each run's
    evaluation.db — stays empty until the user navigates somewhere that
    happens to trigger projection for the right run.

    Projection is incremental (gated by checkpoint + log-size), so this is
    cheap in steady state; the first call after a fresh dismiss replays only
    the actions-log delta.
    """
    if not project_dir.is_dir():
        return
    from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415

    for run_dir in project_dir.iterdir():
        if not run_dir.is_dir():
            continue
        if not (run_dir / "events.jsonl").is_file():
            continue
        try:
            SqliteFindingsRepository(run_dir)._ensure_fresh()  # noqa: SLF001
        except Exception:
            _logger.warning("Projection after mutation failed for %s", run_dir, exc_info=True)


def _rescore_run(
    evaluations_dir: str, project: str, run_id: str | None,
) -> dict[str, Any] | None:
    """Compute the slim rescored payload for the run referenced in a mutation body.

    Returns ``None`` when ``run_id`` is missing or the run directory cannot
    be resolved. When it returns ``None``, the caller also calls
    ``_project_all_runs`` so the action still lands in SQL — otherwise the
    dismissed-tab list (which reads ``WHERE verdict='dismissed'`` from each
    run's evaluation.db) wouldn't see the entry until the user happened to
    trigger projection some other way.

    The payload omits per-finding arrays since dismiss handlers only need
    score/grade fields — see ``_slim_scores`` for the rationale. Callers
    fold the result into the response body so the UI can apply the new
    scores without a follow-up GET.
    """
    if not run_id:
        return None
    try:
        validate_path_segment(run_id)
    except ValueError:
        return None
    from quodeq.services.scoring import get_scores_raw  # noqa: PLC0415

    reports_root = Path(evaluations_dir).resolve()
    try:
        return _slim_scores(get_scores_raw(reports_root, project, run_id))
    except FileNotFoundError:
        return None
    except Exception:
        # Never let a rescore failure break the mutation — the dismiss is
        # already persisted in actions.jsonl. Log and return None so the
        # client falls back to a refetch.
        _logger.warning("Rescore after mutation failed for %s/%s", project, run_id, exc_info=True)
        return None


def rescore_with_fallback(
    evaluations_dir: str, project: str, run_id: str | None,
) -> dict[str, Any] | None:
    """Rescore the requested run, falling back to a project-wide projection.

    Shared by the findings mutation routes and the assistant's
    dismiss_finding action apply. See _rescore_run for the slim payload.
    """
    scores = _rescore_run(evaluations_dir, project, run_id)
    if scores is None:
        proj_dir = _resolve_project_dir(evaluations_dir, project)
        lock = _get_projection_lock(project)

        def _bg_project() -> None:
            # Non-blocking acquire on purpose: skip rather than queue.
            # An in-flight projection already covers the latest actions.
            if not lock.acquire(blocking=False):
                return
            try:
                _project_all_runs(proj_dir)
            finally:
                lock.release()

        threading.Thread(target=_bg_project, daemon=True).start()
    return scores
