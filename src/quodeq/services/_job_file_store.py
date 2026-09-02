"""JSON serialization and disk-backed job store.

Split from ``_job_model.py`` to keep that file under the size ratchet's
300-line cap. ``FileJobStore``/``create_job_store`` stay re-exported from
there. Moved verbatim.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from quodeq.services._job_model import Job, JobStore, _MAX_LOG_LINES

_logger = logging.getLogger(__name__)

_STALE_JOB_AGE_S = 24 * 60 * 60  # 24 hours


def _default_persist_dir() -> Path:
    """Read persist dir from env at call time for lazy configuration.

    Resolution: QUODEQ_JOB_PERSIST_DIR, else ``run/jobs`` next to the index
    DB (mirroring get_score_cache_path, so the test suite's
    QUODEQ_INDEX_DB_PATH override auto-isolates this store too), which
    itself defaults to ``~/.quodeq``. Hardcoding the home fallback here let
    pytest runs write fake jobs into the developer's real dashboard.
    """
    explicit = os.environ.get("QUODEQ_JOB_PERSIST_DIR")
    if explicit:
        return Path(explicit)
    from quodeq.shared._env import get_index_db_path
    return Path(get_index_db_path()).parent / "run" / "jobs"


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


def _job_from_json(data: dict) -> Job:
    """Deserialize a Job from a JSON dict."""
    logs: deque[str] = deque(data.get("logs", []), maxlen=_MAX_LOG_LINES)
    return Job(
        job_id=data["job_id"],
        status=data["status"],
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


class FileJobStore:
    """Job store backed by per-job JSON files on disk.

    Jobs are stored as ``{persist_dir}/{job_id}.json``.  All existing files
    are loaded on init, and stale completed/failed/cancelled jobs older than
    24 hours are cleaned up automatically.
    """

    def __init__(self, persist_dir: Path | None = None) -> None:
        self._persist_dir = persist_dir or _default_persist_dir()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        # SECURITY: restrict directory to owner-only access
        os.chmod(self._persist_dir, 0o700)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._load_all()
        self._cleanup_stale()

    # -- JobStore protocol ---------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def put(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job
            job_data = _job_to_json(job)
        self._write_data(job.job_id, job_data)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)
            path = self._persist_dir / f"{job_id}.json"
            path.unlink(missing_ok=True)

    # -- persistence helpers -------------------------------------------------

    def _write(self, job: Job) -> None:
        """Write a single job to disk. Caller must hold the lock."""
        self._write_data(job.job_id, _job_to_json(job))

    def _write_data(self, job_id: str, data: dict) -> None:
        """Write pre-serialized job data to disk. Does NOT require the lock."""
        path = self._persist_dir / f"{job_id}.json"
        tmp = path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            # SECURITY: restrict job files to owner-only read/write
            os.chmod(tmp, 0o600)
            tmp.replace(path)
            os.chmod(path, 0o600)
        except OSError:
            _logger.warning("Failed to persist job %s", job_id, exc_info=True)
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
                if job.status == "running":
                    job.status = "lost"
                    job.exit_code = None
                    # Stamp an end time or _cleanup_stale (which only prunes
                    # jobs with ended_at) keeps the flipped job forever.
                    if not job.ended_at:
                        job.ended_at = datetime.now(timezone.utc).isoformat()
                    self._jobs[job.job_id] = job
                    self._write(job)
                else:
                    self._jobs[job.job_id] = job
            except (json.JSONDecodeError, KeyError, OSError):
                _logger.warning("Skipping corrupt job file %s", path, exc_info=True)

    def _cleanup_stale(self) -> None:
        """Remove completed/failed/cancelled jobs older than 24 hours."""
        now = time.time()
        stale_ids: list[str] = []
        for job in self._jobs.values():
            if job.status == "running":
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
            _logger.info("Cleaning up stale job %s", jid)
            self._jobs.pop(jid, None)
            (self._persist_dir / f"{jid}.json").unlink(missing_ok=True)


def create_job_store() -> JobStore:
    """Create the default job store.

    Returns a ``FileJobStore`` that persists jobs to ``~/.quodeq/run/jobs/``
    so that job state survives server restarts.
    """
    return FileJobStore()
