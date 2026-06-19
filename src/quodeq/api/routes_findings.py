"""API routes for dismissing and restoring individual findings.

Mutating endpoints (dismiss, restore, delete) accept an optional ``run_id``.
When present, the endpoint returns the rescored payload for that run in the
response body — same shape as ``GET /api/projects/<p>/scores/<run>``. This
lets the UI apply the new scores synchronously from the POST response,
instead of subscribing to an SSE stream and hoping ``scores.updated`` fires
in time. (For the history of why this design exists, see the diagnose
sessions that ended in PRs #525-#528.)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, request

from quodeq.services.deleted import delete_all_dismissed, delete_finding
from quodeq.services.dismissed import dismiss_finding, load_dismissed, restore_finding, restore_all_findings
from quodeq.shared.utils import get_evaluations_dir
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)
_MAX_DISMISSED_LIMIT = 5000


def _project_dir(evaluations_dir: str, project: str) -> Path:
    validate_path_segment(project)
    base = Path(evaluations_dir).resolve()
    resolved = (base / project).resolve()
    if not resolved.is_relative_to(base):
        abort(400, description="Invalid project path")
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


def register_findings_routes(app: Flask) -> None:
    """Register /api/findings/* routes."""

    def _eval_dir() -> str:
        return app.config.get("EVALUATIONS_DIR") or get_evaluations_dir()

    def _scores_with_fallback(
        project: str, run_id: str | None,
    ) -> dict[str, Any] | None:
        """Rescore the requested run, falling back to a project-wide projection.

        When the caller can't supply a usable ``run_id`` (Violations / Map
        nav paths don't carry one today), ``_rescore_run`` returns ``None`` —
        but the action *must* still propagate to SQL or the dismissed-tab
        list won't see it. Project every run as the fallback so the entry
        becomes visible without forcing the UI to retry.
        """
        evaluations_dir = _eval_dir()
        scores = _rescore_run(evaluations_dir, project, run_id)
        if scores is None:
            _project_all_runs(_project_dir(evaluations_dir, project))
        return scores

    @app.get("/api/findings/dismissed")
    def list_dismissed() -> Response:
        project = request.args.get("project", "")
        if not project:
            return jsonify([])
        # No limit param → return everything (capped at the hard maximum).
        # An explicit limit is clamped to [1, _MAX_DISMISSED_LIMIT].
        raw_limit = request.args.get("limit", _MAX_DISMISSED_LIMIT, type=int)
        limit = max(1, min(raw_limit, _MAX_DISMISSED_LIMIT))
        offset = max(0, request.args.get("offset", 0, type=int))
        items = load_dismissed(
            _project_dir(_eval_dir(), project),
            offset=offset,
            limit=limit,
        )
        return jsonify(items)

    @app.post("/api/findings/dismiss")
    def dismiss() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required", "code": "MISSING_PARAM"}), 400
        dismiss_finding(_project_dir(_eval_dir(), project), body)
        scores = _scores_with_fallback(project, run_id)
        return jsonify({"scores": scores}), 200

    @app.post("/api/findings/restore")
    def restore() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        req = body.get("req", "")
        file = body.get("file", "")
        line = body.get("line")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not req or not file or line is None:
            return jsonify({"error": "project, req, file, and line are required", "code": "MISSING_PARAM"}), 400
        restore_finding(_project_dir(_eval_dir(), project), body)
        scores = _scores_with_fallback(project, run_id)
        return jsonify({"scores": scores}), 200

    @app.post("/api/findings/restore-all")
    def restore_all() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project:
            return jsonify({"error": "project is required", "code": "MISSING_PARAM"}), 400
        count = restore_all_findings(_project_dir(_eval_dir(), project))
        scores = _scores_with_fallback(project, run_id)
        return jsonify({"ok": True, "restored": count, "scores": scores}), 200

    @app.post("/api/findings/delete")
    def delete() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        dimension = body.get("dimension", "")
        principle = body.get("principle", "")
        file = body.get("file", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project or not dimension or not principle or not file:
            return jsonify({"error": "project, dimension, principle, and file are required", "code": "MISSING_PARAM"}), 400
        swept = delete_finding(_project_dir(_eval_dir(), project), body)
        scores = _scores_with_fallback(project, run_id)
        return jsonify({"ok": True, "swept": swept, "scores": scores}), 200

    @app.post("/api/findings/delete-all")
    def delete_all() -> tuple[Response, int]:
        body = request.get_json(silent=True) or {}
        project = body.get("project", "")
        run_id = body.get("run_id") or body.get("runId")
        if not project:
            return jsonify({"error": "project is required", "code": "MISSING_PARAM"}), 400
        count = delete_all_dismissed(_project_dir(_eval_dir(), project))
        scores = _scores_with_fallback(project, run_id)
        return jsonify({"ok": True, "deleted": count, "scores": scores}), 200
