"""Post-run hook: runs after a JobManager job reaches a terminal state.

Wraps the two things that have to happen when an evaluation finishes —
ephemeral clone cleanup and event-log projection into evaluation.db —
behind a single callable so JobManager only sees one ``on_job_complete``
target. Each step is also exposed as its own method for direct testing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from quodeq.services._ephemeral_cleanup import maybe_cleanup_after_job

_logger = logging.getLogger(__name__)


class PostRunHook:
    """``on_job_complete`` target for JobManager.

    Construct once with the active reports root (or ``None`` to fall back
    to the env var at call time) and pass the instance directly to
    ``JobManager(on_job_complete=hook)``.
    """

    def __init__(self, reports_root: Path | None = None) -> None:
        self._reports_root = reports_root

    def __call__(self, job_id: str, job: Any) -> None:
        project_uuid = getattr(job, "output_project", None)
        if not project_uuid:
            return
        reports = Path(self._reports_root) if self._reports_root is not None else _default_reports_root()
        self.cleanup_clone(project_uuid, reports)
        try:
            self.project_events(job_id, job, reports)
        except Exception:
            _logger.warning(
                "Post-run projection failed for job %s — State Store may be incomplete",
                job_id,
                exc_info=True,
            )

    @staticmethod
    def cleanup_clone(project_uuid: str, reports_root: Path) -> None:
        """Delete the ephemeral clone (if any) for *project_uuid*."""
        from quodeq.shared._env import get_clones_dir
        maybe_cleanup_after_job(
            reports_root=Path(reports_root),
            project_uuid=project_uuid,
            clones_root=Path(get_clones_dir()),
        )

    @staticmethod
    def project_events(job_id: str, job: Any, reports_root: Path) -> None:
        """Project ``events.jsonl`` into ``evaluation.db`` for the run.

        No-op when the run has no events log. Raises on projection failure.
        """
        project_uuid = getattr(job, "output_project", None)
        run_id = getattr(job, "output_run_id", None)
        if not project_uuid or not run_id:
            return
        run_dir = Path(reports_root) / project_uuid / run_id
        events_log = run_dir / "events.jsonl"
        if not events_log.is_file():
            return
        from quodeq.data.projection.projector import Projector
        result = Projector().project(events_log, run_dir)
        _logger.info(
            "Projected %d events for %s/%s (rebuilt=%s)",
            result.events_projected, project_uuid, run_id, result.rebuilt,
        )


def _default_reports_root() -> Path:
    from quodeq.shared._env import get_evaluations_dir
    return Path(get_evaluations_dir())
