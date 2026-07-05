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


def _resolve_default_run_id(evaluations_dir: str, project: str) -> str | None:
    """Return the run_id the Overview lands on by default, or None.

    Reuses the EXACT "latest completed run" rule the dashboard uses: pick the
    first run in newest-first ``list_runs`` order whose status is eligible for
    the default view (``complete`` only), falling back to the newest run when
    none is complete. This mirrors ``dashboard._resolve_selected_run("latest")``
    so ``isLatest`` matches what the Overview actually shows.
    """
    from quodeq.services.dim_resolution import is_eligible_for_default_view  # noqa: PLC0415
    from quodeq.services.ports import list_runs  # noqa: PLC0415

    reports_root = Path(evaluations_dir).resolve()
    try:
        runs = list_runs(reports_root, project)
    except Exception:
        return None
    if not runs:
        return None
    selected = next(
        (r for r in runs if is_eligible_for_default_view(r.status)),
        runs[0],
    )
    return selected.run_id


def _accumulated_payload(evaluations_dir: str, project: str) -> dict[str, Any] | None:
    """Return the cache-backed accumulated payload, or None on any failure.

    ``get_project_scores(reports_root, project, None)`` returns a dict with an
    ``accumulated`` key ({dimensions, summary}); we surface just that so the
    client can patch the accumulated (cross-run) scores cache.
    """
    from quodeq.services.scoring import get_project_scores  # noqa: PLC0415

    reports_root = Path(evaluations_dir).resolve()
    try:
        payload = get_project_scores(reports_root, project, None)
    except Exception:
        _logger.warning("Accumulated fetch for delta failed for %s", project, exc_info=True)
        return None
    if not payload:
        return None
    return payload.get("accumulated")


def _mutation_envelope(
    evaluations_dir: str, project: str, run_id: str | None, kind: str,
) -> dict[str, Any]:
    """Shared delta scaffold: kind/runId/isLatest/accumulated.

    ``isLatest`` is True when ``run_id`` is the run the Overview lands on by
    default — the exact ``_resolve_default_run_id`` rule shared with the
    dashboard. ``accumulated`` carries the (cache-backed) cross-run rollup so
    the Overview's accumulated view updates without a refetch; it is None when
    no ``run_id`` was supplied (the caller has no run to anchor the rollup to)
    or when the fetch fails. Per-kind finding fields (``dismissed`` /
    ``restored`` / ``deleted``) are folded in by the caller — bulk kinds
    (``restore_all`` / ``delete_all``) carry none.
    """
    is_latest = False
    accumulated: dict[str, Any] | None = None
    if run_id:
        is_latest = run_id == _resolve_default_run_id(evaluations_dir, project)
        accumulated = _accumulated_payload(evaluations_dir, project)
    return {
        "kind": kind,
        "runId": run_id,
        "isLatest": is_latest,
        "accumulated": accumulated,
    }


def dismiss_delta(
    evaluations_dir: str, project: str, run_id: str | None, dismissed: dict[str, Any],
) -> dict[str, Any]:
    """Describe a dismiss mutation so the client can patch its caches.

    The client splices the dismissed finding out of the run-detail violation
    list locally (it has the full key) and patches scores + accumulated.
    """
    envelope = _mutation_envelope(evaluations_dir, project, run_id, "dismiss")
    envelope["dismissed"] = {
        "req": dismissed.get("req"),
        "file": dismissed.get("file"),
        "line": dismissed.get("line"),
    }
    return envelope


def restore_delta(
    evaluations_dir: str, project: str, run_id: str | None, restored: dict[str, Any],
) -> dict[str, Any]:
    """Describe a restore mutation so the client can patch its caches.

    Unlike dismiss, the client can't reconstruct the restored violation body,
    so it patches scores + accumulated and INVALIDATES the run-detail violation
    source (refetch on next view). ``restored`` carries the finding key.
    """
    envelope = _mutation_envelope(evaluations_dir, project, run_id, "restore")
    envelope["restored"] = {
        "req": restored.get("req"),
        "file": restored.get("file"),
        "line": restored.get("line"),
    }
    return envelope


def delete_delta(
    evaluations_dir: str, project: str, run_id: str | None, deleted: dict[str, Any],
) -> dict[str, Any]:
    """Describe a delete mutation so the client can patch its caches.

    Delete sweeps every finding sharing (dimension, principle, file), so the
    client can't cheaply mirror the batch removal — it patches scores +
    accumulated and INVALIDATES the run-detail violation source.
    """
    envelope = _mutation_envelope(evaluations_dir, project, run_id, "delete")
    envelope["deleted"] = {
        "dimension": deleted.get("dimension"),
        "principle": deleted.get("principle"),
        "file": deleted.get("file"),
    }
    return envelope


def restore_all_delta(
    evaluations_dir: str, project: str, run_id: str | None,
) -> dict[str, Any]:
    """Describe a bulk restore-all mutation (no single finding key)."""
    return _mutation_envelope(evaluations_dir, project, run_id, "restore_all")


def delete_all_delta(
    evaluations_dir: str, project: str, run_id: str | None,
) -> dict[str, Any]:
    """Describe a bulk delete-all mutation (no single finding key)."""
    return _mutation_envelope(evaluations_dir, project, run_id, "delete_all")


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
