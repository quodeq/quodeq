"""Rescore-after-mutation helpers, shared by API routes and assistant actions.

Moved out of ``api/routes_findings.py`` so the assistant's dismiss action can
reuse ``rescore_with_fallback`` without an assistant -> api layer import.
Behavior is unchanged: rescore the referenced run when possible, otherwise
kick a background projection so the mutation still lands in SQL. Distinct
from ``services/rescore.py``, which is the in-memory grade recompute engine.

Split: per-project locks + the project-wide projection sweep moved
to ``_mutation_projection.py``; the slim rescore payload + default-run
resolution moved to ``_mutation_scoring.py``. Both are re-exported here —
``ProjectLockRegistry``/``DEFAULT_PROJECT_LOCKS`` and ``project_all_runs``
are imported directly by tests, which patch/inspect them at this module's
path.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from quodeq.services.background import BackgroundRunner, ThreadBackgroundRunner
from quodeq.services._mutation_projection import (  # noqa: F401 — re-export
    ProjectLockRegistry,
    DEFAULT_PROJECT_LOCKS,
    get_projection_lock,
    project_all_runs,
    resolve_project_dir,
)
from quodeq.services._mutation_scoring import (  # noqa: F401 — re-export
    rescore_run,
    resolve_default_run_id,
    slim_scores,
)
from quodeq.shared.fault_isolation import run_isolated
from quodeq.shared.log_sink import LoggerSink

logger = logging.getLogger(__name__)
# What the LogSink-typed callees get. A bare Logger has no ``success``.
_log_sink = LoggerSink(logger)
# One bounded runner for every fallback projection in the process. It holds
# no threads while idle (workers exit on an empty queue), so a module-level
# instance costs nothing until a fallback actually fires.
_SHARED_RUNNER = ThreadBackgroundRunner(log=_log_sink)


def _mutation_envelope(
    evaluations_dir: str, project: str, run_id: str | None, kind: str,
) -> dict[str, Any]:
    """Shared delta scaffold: kind/runId/isLatest.

    ``isLatest`` is True when ``run_id`` is the run the Overview lands on by
    default — the exact ``resolve_default_run_id`` rule shared with the
    dashboard. Per-kind finding fields (``dismissed`` / ``restored`` /
    ``deleted``) are folded in by the caller — bulk kinds (``restore_all`` /
    ``delete_all``) carry none.

    ``accumulated`` is intentionally ALWAYS None. The client derives the
    Overview's per-dimension grades from the (fast, ~0.1s) single-run rescore
    returned alongside this delta in ``scores`` — the accumulated entry for a
    dimension the latest run owns equals that run's rescored dimension. We used
    to compute the full cross-run rollup here, but that ran ``compute_accumulated``
    over every run (~100s cold on large projects, and recomputed on EVERY
    mutation because the dismissed-set hash changes), which blew past the
    client's 30s timeout. The request then aborted, the client never applied the
    delta, and the Overview grade only refreshed on a later window-focus
    refetch. See ``applyMutationDelta`` for the client-side derivation; the
    weighted overall summary is left to a lazy refetch to avoid duplicating the
    grade formula on the client.
    """
    is_latest = bool(run_id) and run_id == resolve_default_run_id(evaluations_dir, project)
    return {
        "kind": kind,
        "runId": run_id,
        "isLatest": is_latest,
        "accumulated": None,
    }


def dismiss_delta(
    evaluations_dir: str, project: str, run_id: str | None, dismissed: dict[str, Any],
) -> dict[str, Any]:
    """Describe a dismiss mutation so the client can patch its caches.

    The client splices the dismissed finding out of the run-detail violation
    list locally (it has the full key), patches the per-run scores, and derives
    the Overview accumulated dimension grades from the rescored ``scores``.
    """
    envelope = _mutation_envelope(evaluations_dir, project, run_id, "dismiss")
    envelope["dismissed"] = {
        "req": dismissed.get("req"),
        "file": dismissed.get("file"),
        "line": dismissed.get("line"),
    }
    # Name the project so the assistant apply handler patches the cache keyed
    # on the delta's own project, not the live-selected one. The manual route
    # passes its own projectId to applyMutationDelta and ignores this field, so
    # this is additive. Kept here (not in _mutation_envelope) to limit the blast
    # radius to the one kind the assistant forwards.
    envelope["project"] = project
    return envelope


def restore_delta(
    evaluations_dir: str, project: str, run_id: str | None, restored: dict[str, Any],
) -> dict[str, Any]:
    """Describe a restore mutation so the client can patch its caches.

    Unlike dismiss, the client can't reconstruct the restored violation body,
    so it patches the per-run scores (deriving the Overview accumulated
    dimension grades from them) and INVALIDATES the run-detail violation source
    (refetch on next view). ``restored`` carries the finding key.
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
    client can't cheaply mirror the batch removal — it patches the per-run
    scores (deriving the Overview accumulated dimension grades from them) and
    INVALIDATES the run-detail violation source.
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


def _project_all_runs_and_release(proj_dir: Path, lock: threading.Lock) -> None:
    """Run the project-wide projection sweep; always release *lock* after.

    Called only once *lock* is already held (see _try_project_all_runs).
    No ``log=`` kwarg: tests patch ``project_all_runs`` wholesale with a bare
    ``(project_dir)`` side_effect, so the call site must stay
    single-positional-arg compatible. The NULL_LOG default means an
    individual run's own projection failure is already logged at warning by
    ``project_all_runs`` itself (it falls back to this module's logger when
    no log is injected); a failure escaping ``project_all_runs`` itself
    (e.g. a directory-listing or repo-factory error) is caught at the
    ``_bg_project`` boundary instead.
    """
    try:
        project_all_runs(proj_dir)
    finally:
        lock.release()


def _try_project_all_runs(proj_dir: Path, lock: threading.Lock) -> None:
    """Acquire *lock* non-blockingly and, if won, run the projection sweep.

    Skips (rather than queues) when another projection for the same project
    already holds the lock -- it already covers the latest actions.
    """
    if lock.acquire(blocking=False):
        _project_all_runs_and_release(proj_dir, lock)


def rescore_with_fallback(
    evaluations_dir: str, project: str, run_id: str | None,
    *, runner: BackgroundRunner | None = None,
) -> dict[str, Any] | None:
    """Rescore the requested run, falling back to a project-wide projection.

    Shared by the findings mutation routes and the assistant's
    dismiss_finding action apply. See rescore_run for the slim payload.
    *runner* lets callers/tests inject a synchronous or fake BackgroundRunner;
    production uses the module's one bounded ``_SHARED_RUNNER``. No task is
    submitted while a projection for *project* already holds its lock: that
    projection covers the latest actions, and queueing a duplicate would only
    fill the bounded queue.
    """
    scores = rescore_run(evaluations_dir, project, run_id, log=_log_sink)
    if scores is None:
        proj_dir = resolve_project_dir(evaluations_dir, project)
        lock = get_projection_lock(project)
        if lock.locked():
            return scores

        def _bg_project() -> None:
            run_isolated(
                lambda: _try_project_all_runs(proj_dir, lock),
                label=f"background projection fallback for project {project!r} (run_id={run_id!r})",
                log=logger,
            )

        (runner or _SHARED_RUNNER).submit(
            _bg_project, name=f"rescore-project-{project}",
        )
    return scores
