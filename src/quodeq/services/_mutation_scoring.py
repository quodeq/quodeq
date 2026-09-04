"""Slim rescore payload and default-run resolution for mutation deltas.

Split (Task 14) out of ``mutation_rescore.py``. ``mutation_rescore.py`` is a
DECLARED_LOGGING_SITES entry (still imports stdlib ``logging``); this sibling
originally avoided a new logging import, routing ``_rescore_run``'s failure
log through an injected ``LogSink`` instead. Task C6 (usability sweep) added
a stdlib ``_logger`` for ``_resolve_default_run_id``'s previously-silent
``list_runs`` failure -- this module is now its own DECLARED_LOGGING_SITES
entry too (see ``tests/tools/test_logging_boundary.py``).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services._wiring import list_runs
from quodeq.shared.validation import validate_path_segment

_logger = logging.getLogger(__name__)


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


def _rescore_run(
    evaluations_dir: str, project: str, run_id: str | None,
    *, log: LogSink = NULL_LOG,
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
    except Exception as exc:  # noqa: BLE001
        # Never let a rescore failure break the mutation — the dismiss is
        # already persisted in actions.jsonl. Log and return None so the
        # client falls back to a refetch.
        log.warning(f"Rescore after mutation failed for {project}/{run_id}: {exc}")
        return None


def _resolve_default_run_id(evaluations_dir: str, project: str) -> str | None:
    """Return the run_id the Overview lands on by default, or None.

    Reuses the EXACT "latest completed run" rule the dashboard uses: pick the
    first run in newest-first ``list_runs`` order whose status is eligible for
    the default view (``complete`` only), falling back to the newest run when
    none is complete. This mirrors ``dashboard._resolve_selected_run("latest")``
    so ``isLatest`` matches what the Overview actually shows.
    """
    from quodeq.services.scoring_view import is_eligible_for_default_view  # noqa: PLC0415

    reports_root = Path(evaluations_dir).resolve()
    try:
        runs = list_runs(reports_root, project)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("Failed to resolve default run for %s: %s", project, exc)
        return None
    if not runs:
        return None
    selected = next(
        (r for r in runs if is_eligible_for_default_view(r.status)),
        runs[0],
    )
    return selected.run_id
