"""JSON serialization and disk-backed job store.

``FileJobStore``/``create_job_store`` are re-exported from ``_job_model.py``.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

# logger threaded from _job_model.py (not a fresh logging.getLogger here) --
# this module stays inside the SEP-06 logging boundary that _job_model.py
# already carries a declared exemption for (see
# tests/tools/test_logging_boundary.py's DECLARED_LOGGING_SITES).
from quodeq.config.services_env import job_persist_dir as _resolve_job_persist_dir
from quodeq.core.run.job_status import JobStatus, parse_job_status
from quodeq.shared.clock import utc_now_iso
from quodeq.services._job_model import InMemoryJobStore, Job, JobStore, MAX_LOG_LINES, logger

_STALE_JOB_AGE_S = 24 * 60 * 60  # 24 hours


def _default_persist_dir(env: Mapping[str, str] | None = None) -> Path:
    """Read persist dir from env at call time for lazy configuration.

    *env* overrides ``os.environ`` for the ``QUODEQ_JOB_PERSIST_DIR`` read.
    See ``config.services_env.job_persist_dir`` for the resolution order.
    """
    return _resolve_job_persist_dir(env=env)


def _job_to_json(job: Job) -> dict:
    """Serialize a Job to a JSON-safe dict (no Process objects)."""
    return {
        "job_id": job.job_id,
        "status": job.status,
        "command": job.command,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "exit_code": job.exit_code,
        "logs": list(job.logs),
        "output_project": job.output_project,
        "output_run_id": job.output_run_id,
        "phase": job.phase,
        "deadline_at": job.deadline_at,
        "current_dimension": job.current_dimension,
        "dimensions": job.dimensions,
        "ai_provider": job.ai_provider,
        "ai_model": job.ai_model,
        "time_limit_s": job.time_limit_s,
        "exit_reason": job.exit_reason,
    }


def _status_from_json(raw: object) -> JobStatus | object:
    """The JobStatus a job file's status means; an unknown or non-string value stays raw, logged.

    A job file must never become unreadable over its status word.
    """
    if not isinstance(raw, str):
        logger.warning("job file with non-string status %r kept as-is", raw)
        return raw
    try:
        return parse_job_status(raw)
    except ValueError:
        logger.warning("job file with unknown status %r kept as-is", raw)
        return raw


def _job_from_json(data: dict) -> Job:
    """Deserialize a Job from a JSON dict."""
    logs: deque[str] = deque(data.get("logs", []), maxlen=MAX_LOG_LINES)
    return Job(
        job_id=data["job_id"],
        status=_status_from_json(data["status"]),
        command=data.get("command", []),
        started_at=data.get("started_at", ""),
        ended_at=data.get("ended_at"),
        exit_code=data.get("exit_code"),
        logs=logs,
        output_project=data.get("output_project"),
        output_run_id=data.get("output_run_id"),
        phase=data.get("phase"),
        deadline_at=data.get("deadline_at"),
        current_dimension=data.get("current_dimension"),
        dimensions=data.get("dimensions"),
        ai_provider=data.get("ai_provider"),
        ai_model=data.get("ai_model"),
        time_limit_s=data.get("time_limit_s"),
        exit_reason=data.get("exit_reason"),
    )


class FileJobStore(InMemoryJobStore):
    """Job store backed by per-job JSON files on disk.

    Jobs are stored as ``{persist_dir}/{job_id}.json``.  All existing files
    are loaded on init, and stale completed/failed/cancelled jobs older than
    24 hours are cleaned up automatically.

    The in-memory dict, its lock, and the read-only ``get``/``list`` come
    from :class:`InMemoryJobStore`; this store adds the disk write on every
    mutation.
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._persist_dir = persist_dir or _default_persist_dir()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        # SECURITY: restrict directory to owner-only access
        os.chmod(self._persist_dir, 0o700)
        super().__init__()
        self._load_all()
        self._cleanup_stale()

    # -- JobStore protocol ---------------------------------------------------

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
            job_data = _job_to_json(job)
        self._write_data(job.job_id, job_data)

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            self._job_path(job_id).unlink(missing_ok=True)

    # -- persistence helpers -------------------------------------------------

    def _job_path(self, job_id: str) -> Path:
        """Where *job_id*'s record lives: ``{persist_dir}/{job_id}.json``."""
        return self._persist_dir / f"{job_id}.json"

    def _write(self, job: Job) -> None:
        """Write a single job to disk. Caller must hold the lock."""
        self._write_data(job.job_id, _job_to_json(job))

    def _write_data(self, job_id: str, data: dict) -> None:
        """Write pre-serialized job data to disk. Does NOT require the lock."""
        path = self._job_path(job_id)
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            # SECURITY: restrict job files to owner-only read/write
            os.chmod(tmp, 0o600)
            tmp.replace(path)
            os.chmod(path, 0o600)
        except OSError:
            logger.warning("Failed to persist job %s", job_id, exc_info=True)
            tmp.unlink(missing_ok=True)

    def _load_all(self) -> None:
        """Load every .json file in the persist dir."""
        for path in self._persist_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                job = _job_from_json(data)
                # Jobs that were 'running' when the server went down lose
                # their monitor thread, but the subprocess itself was
                # spawned start_new_session=True and usually survives — the
                # run may well still be alive and writing status.json. Mark
                # the job 'lost' (tracking gone), NOT 'failed': the merged
                # evaluations list then yields to the truthful ext- index
                # row for the same run, which can still track and cancel it.
                if job.status == JobStatus.RUNNING:
                    job.status = JobStatus.LOST
                    job.exit_code = None
                    # Stamp an end time or _cleanup_stale (which only prunes
                    # jobs with ended_at) keeps the flipped job forever.
                    if not job.ended_at:
                        job.ended_at = utc_now_iso()
                    self._jobs[job.job_id] = job
                    self._write(job)
                else:
                    self._jobs[job.job_id] = job
            except (json.JSONDecodeError, KeyError, OSError):
                logger.warning("Skipping corrupt job file %s", path, exc_info=True)

    def _cleanup_stale(self) -> None:
        """Remove completed/failed/cancelled jobs older than 24 hours."""
        now = time.time()
        stale_ids: list[str] = []
        for job in self._jobs.values():
            if job.status == JobStatus.RUNNING:
                continue
            if not job.ended_at:
                continue
            try:
                ended = datetime.fromisoformat(job.ended_at)
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=timezone.utc)
                age = now - ended.timestamp()
                if age > _STALE_JOB_AGE_S:
                    stale_ids.append(job.job_id)
            except (ValueError, TypeError):
                continue
        for jid in stale_ids:
            logger.info("Cleaning up stale job %s", jid)
            self._jobs.pop(jid, None)
            self._job_path(jid).unlink(missing_ok=True)


def create_job_store() -> JobStore:
    """Create the default job store.

    Returns a ``FileJobStore`` that persists jobs to ``~/.quodeq/run/jobs/``
    so that job state survives server restarts.
    """
    return FileJobStore()
