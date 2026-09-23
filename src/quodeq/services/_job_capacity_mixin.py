"""JobManager's start_job concurrency cap.

Split from ``jobs.py`` to keep that file under the file-length ratchet.
Mixed into ``JobManager`` there; expects ``self._lock``, ``self._processes``,
``self._reserved``, ``self._store``, and ``self._log`` to already be set by
``JobManager.__init__``.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from quodeq.core.run.job_status import JobStatus
from quodeq.core.types import JobSnapshot
from quodeq.services._job_model import Job
from quodeq.shared.env import env_int

_DEFAULT_MAX_CONCURRENT_JOBS = 8
_EXIT_CODE_TOO_MANY_JOBS = -2


class _JobCapacityMixin:
    @staticmethod
    def _max_concurrent_jobs() -> int:
        """Return QUODEQ_MAX_CONCURRENT_JOBS, or 8 when unset/invalid."""
        return env_int("QUODEQ_MAX_CONCURRENT_JOBS", _DEFAULT_MAX_CONCURRENT_JOBS, minimum=1)

    def _reserve_slot_or_refuse(self, job: Job) -> JobSnapshot | None:
        """Reserve a slot for *job*, or fail it as a capacity refusal.

        Returns None once the slot is reserved, and the caller MUST then
        release it: ``_processes[job_id] = process`` under ``self._lock``
        after a successful spawn, or ``_release_slot`` on failure.

        The reservation is what makes the cap hold. Counting only
        ``self._processes`` left the window between the check and the spawn
        open, so concurrent starts could all pass at cap-1. A reserved id is
        deliberately NOT a placeholder in ``_processes``: shutdown and cancel
        iterate that dict and call ``.pid`` on what they find.

        Mirrors the spawn-failure path in ``start_job``: same store write,
        same ``error=`` return.
        """
        cap = self._max_concurrent_jobs()
        with self._lock:
            running = len(self._processes) + len(self._reserved)
            if running < cap:
                self._reserved.add(job.job_id)
                return None
        message = (
            f"Too many evaluations running ({running}); wait for one to "
            "finish or raise QUODEQ_MAX_CONCURRENT_JOBS."
        )
        self._log.error(message)
        job.status = JobStatus.FAILED
        job.ended_at = datetime.now(timezone.utc).isoformat()
        job.exit_code = _EXIT_CODE_TOO_MANY_JOBS
        job.logs.append(message)
        with self._lock:
            self._store.put(job)
        result = job.to_dict()
        return replace(result, error=message)

    def _release_slot(self, job_id: str) -> None:
        """Give back a reservation that never became a process."""
        with self._lock:
            self._reserved.discard(job_id)
