"""Background job management for evaluation subprocesses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import threading
import uuid
from typing import Any, Iterable

import subprocess

MAX_LOG_LINES = 600  # rolling buffer size for per-job log lines
REPORT_PATH_RE = re.compile(r"Report path:.*[/\\]([^/\\\s]+)[/\\]([^/\\\s]+)[/\\]evaluation")


@dataclass
class Job:
    """State of a single evaluation subprocess."""

    job_id: str
    status: str
    command: list[str]
    started_at: str
    ended_at: str | None
    exit_code: int | None
    logs: list[str]
    output_project: str | None
    output_run_id: str | None
    phase: str | None = None
    current_dimension: str | None = None
    dimensions: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the job state to a JSON-compatible dict."""
        return {
            "jobId": self.job_id,
            "status": self.status,
            "command": " ".join(self.command),
            "startedAt": self.started_at,
            "endedAt": self.ended_at,
            "exitCode": self.exit_code,
            "logs": list(self.logs),
            "outputProject": self.output_project,
            "outputRunId": self.output_run_id,
            "phase": self.phase,
            "currentDimension": self.current_dimension,
            "dimensions": self.dimensions,
        }


class JobManager:
    """Thread-safe manager for spawning and tracking evaluation subprocesses."""

    def __init__(self, spawn_impl=None) -> None:
        self._spawn = spawn_impl or subprocess.Popen
        self._jobs: dict[str, Job] = {}
        self._processes: dict[str, Any] = {}
        self._lock = threading.Lock()

    def start_job(self, cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
        """Spawn a subprocess and return its initial job state."""
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            status="running",
            command=cmd,
            started_at=datetime.now(timezone.utc).isoformat(),
            ended_at=None,
            exit_code=None,
            logs=[],
            output_project=None,
            output_run_id=None,
        )

        process = self._spawn(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )

        with self._lock:
            self._jobs[job_id] = job
            self._processes[job_id] = process

        threading.Thread(target=self._consume_stream, args=(job_id, process.stdout), daemon=True).start()
        threading.Thread(target=self._consume_stream, args=(job_id, process.stderr), daemon=True).start()
        threading.Thread(target=self._monitor_process, args=(job_id, process), daemon=True).start()

        return job.to_dict()

    def cancel_job(self, job_id: str) -> bool:
        """Terminate a running job. Return True if cancelled successfully."""
        with self._lock:
            job = self._jobs.get(job_id)
            process = self._processes.get(job_id)
            if not job or job.status != "running":
                return False
            job.status = "cancelled"
            job.ended_at = datetime.now(timezone.utc).isoformat()
        if process:
            process.terminate()
        return True

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        """Return the current state of a job, or None if not found."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return job.to_dict()

    def list_jobs(self) -> list[dict[str, Any]]:
        """Return all tracked jobs as serialized dicts."""
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def _append_log(self, job: Job, line: str) -> None:
        if not line:
            return
        # Parse structured markers — update state but don't show in console
        if line.startswith('{"_cc"'):
            try:
                marker = json.loads(line)
                phase = marker.get("_cc")
                if phase == "setup":
                    job.phase = "setup"
                    job.dimensions = marker.get("dimensions")
                elif phase == "analyzing":
                    job.current_dimension = marker.get("dimension")
                    job.phase = "analyzing"
                elif phase == "scoring":
                    job.current_dimension = marker.get("dimension")
                    job.phase = "scoring"
            except json.JSONDecodeError:
                pass  # Malformed marker line — skip silently; not a user-visible log
            return
        job.logs.append(line)
        if len(job.logs) > MAX_LOG_LINES:
            job.logs[:] = job.logs[-MAX_LOG_LINES:]
        match = REPORT_PATH_RE.search(line)
        if match:
            job.output_project = match.group(1)
            job.output_run_id = match.group(2)

    def _consume_stream(self, job_id: str, stream: Iterable[str] | None) -> None:
        if stream is None:
            return
        for line in stream:
            stripped = line.rstrip("\n")
            with self._lock:
                job = self._jobs.get(job_id)
                if not job:
                    return
                self._append_log(job, stripped)

    def _monitor_process(self, job_id: str, process: subprocess.Popen) -> None:
        exit_code = process.wait()
        with self._lock:
            self._processes.pop(job_id, None)
            job = self._jobs.get(job_id)
            if not job or job.status == "cancelled":
                return
            job.exit_code = exit_code
            job.ended_at = datetime.now(timezone.utc).isoformat()
            job.status = "done" if exit_code == 0 else "failed"
