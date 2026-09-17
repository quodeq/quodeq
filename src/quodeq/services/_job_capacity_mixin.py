"""JobManager's start_job concurrency cap.

Split from ``jobs.py`` to keep that file under the file-length ratchet.
Mixed into ``JobManager`` there; expects ``self._lock``, ``self._processes``,
``self._store``, and ``self._log`` to already be set by
``JobManager.__init__``.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from quodeq.core.types import JobSnapshot
from quodeq.services._job_model import Job
from quodeq.shared._env import env_int

_DEFAULT_MAX_CONCURRENT_JOBS = 8
_EXIT_CODE_TOO_MANY_JOBS = -2


class _JobCapacityMixin:
    @staticmethod
    def _max_concurrent_jobs() -> int:
        """Return QUODEQ_MAX_CONCURRENT_JOBS, or 8 when unset/invalid."""
        return env_int("QUODEQ_MAX_CONCURRENT_JOBS", _DEFAULT_MAX_CONCURRENT_JOBS, minimum=1)

    def _refuse_if_at_capacity(self, job: Job) -> JobSnapshot | None:
        """Fail *job* as a capacity refusal if the running-job cap is hit.

        Mirrors the spawn-failure path in ``start_job``: same store write,
        same ``error=`` return. Returns None when there is room to spawn.
        """
        with self._lock:
            running = len(self._processes)
        if running < self._max_concurrent_jobs():
            return None
        message = (
            f"Too many evaluations running ({running}); wait for one to "
            "finish or raise QUODEQ_MAX_CONCURRENT_JOBS."
        )
        self._log.error(message)
        from quodeq.services.jobs import STATUS_FAILED  # noqa: PLC0415 -- avoids a jobs.py <-> mixin import cycle
        job.status = STATUS_FAILED
        job.ended_at = datetime.now(timezone.utc).isoformat()
        job.exit_code = _EXIT_CODE_TOO_MANY_JOBS
        job.logs.append(message)
        with self._lock:
            self._store.put(job)
        result = job.to_dict()
        return replace(result, error=message)
