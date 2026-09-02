"""Per-project projection locks and the project-wide SQL projection sweep.

Split (Task 14) out of ``mutation_rescore.py``. ``mutation_rescore.py`` is a
DECLARED_LOGGING_SITES entry (still imports stdlib ``logging``); this sibling
does not add a new logging import, so ``_project_all_runs`` accepts an
injected ``LogSink`` and, when none is passed, deferred-imports the facade's
own declared ``_logger`` at the failure site — restoring the original
exc-path logging without a new ``getLogger`` call here and without changing
the (test-pinned) single-positional-arg production call site.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.shared.validation import validate_path_segment


class ProjectLockRegistry:
    """Per-project locks for background projection.

    Intentionally unbounded: one tiny Lock object per distinct project name
    that has ever triggered a background projection on this host.  In practice
    this mirrors the number of projects on disk, which is small and naturally
    bounded by real usage.  Contrast with _scored_jobs (bounded LRU) — scored
    jobs can accumulate many run-ids per project, so a size cap there is
    meaningful; here there is one entry per project, not per run.

    The default registry below is process-wide on purpose; tests inject a
    fresh one so lock state never leaks between them.
    """

    def __init__(self) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, project: str) -> threading.Lock:
        """Return (and lazily create) the Lock for *project*."""
        with self._guard:
            if project not in self._locks:
                self._locks[project] = threading.Lock()
            return self._locks[project]

    def clear(self) -> None:
        with self._guard:
            self._locks.clear()


_DEFAULT_PROJECT_LOCKS = ProjectLockRegistry()


def _get_projection_lock(project: str, registry: ProjectLockRegistry | None = None) -> threading.Lock:
    """Return the Lock for *project* from *registry* (default: process-wide)."""
    return (registry or _DEFAULT_PROJECT_LOCKS).get(project)


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


def _project_all_runs(
    project_dir: Path,
    repo_factory: Callable[[Path], Any] | None = None,
    *, log: LogSink = NULL_LOG,
) -> None:
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
    if repo_factory is None:
        from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository  # noqa: PLC0415
        repo_factory = SqliteFindingsRepository

    for run_dir in sorted(p for p in project_dir.iterdir() if p.is_dir()):
        if not (run_dir / "events.jsonl").is_file():
            continue
        try:
            repo_factory(run_dir).ensure_projected()
        except Exception as exc:  # noqa: BLE001
            if log is NULL_LOG:
                # No caller-injected log (the production call site can't pass
                # one — tests patch this whole function with a bare
                # single-arg side_effect). Fall back to the facade's own
                # declared logger instead of a new getLogger() here.
                from quodeq.services.mutation_rescore import _logger as log  # noqa: PLC0415
            log.warning(f"Projection after mutation failed for {run_dir}: {exc}")
