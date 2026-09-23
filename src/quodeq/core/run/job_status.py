"""Job status vocabulary (pure; persistence in services/_job_file_store).

A job is the process wrapper around a run. Its status spells the same words
as ``RunState`` where the meanings coincide, plus ``lost`` for a job whose
process disappeared with the server (``_job_file_store`` flips a persisted
``running`` job to ``lost`` on startup). Jobs never persist ``pending`` or
``finalizing``.
"""
from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """The statuses a job passes through, as persisted in the job file."""

    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LOST = "lost"


JOB_TERMINAL: frozenset[JobStatus] = frozenset(
    {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.LOST}
)

# Excludes LOST on purpose: a lost job's subprocess may still be alive and
# writing (the tracking thread, not the process, is what was lost), so
# callers that decide "the run actually finished" (SSE done-frame, is_complete
# disk fallback, preparing-job liveness) must not treat LOST as finished --
# they fall through to a status.json/disk check instead. Use JOB_TERMINAL
# only where "no longer tracked, for any reason including lost" is the point.
JOB_FINISHED: frozenset[JobStatus] = frozenset(
    {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}
)

# Job ids of runs launched outside the dashboard (CLI, CI) carry this prefix
# so the evaluations index can tell them from dashboard-managed jobs.
EXTERNAL_JOB_PREFIX = "ext-"


def is_external_job_id(job_id: str) -> bool:
    """True for a job id minted by an external launcher."""
    return job_id.startswith(EXTERNAL_JOB_PREFIX)


def strip_external_prefix(job_id: str) -> str:
    """The run id behind an external job id; other ids are returned as-is."""
    return job_id[len(EXTERNAL_JOB_PREFIX):] if is_external_job_id(job_id) else job_id
