"""Log-tailing and log-path-resolution helpers for the log-stream routes.

Raw file I/O and the log-parsing business rules used by
``_log_stream_routes.py`` live here rather than in the routes module, the same
layout ``_sse_log_helpers.py`` uses for the SSE tail generator.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from http import HTTPStatus
from pathlib import Path

from quodeq.api._sse_log_helpers import tail_max_bytes
from quodeq.core.run.job_status import JOB_FINISHED, JobStatus
from quodeq.services.run_events import read_run_status_json

_logger = logging.getLogger(__name__)

# Lines containing this marker are kept in run.log for forensics but suppressed
# from the dashboard's live console — they're per-minute resource snapshots
# (rss / fds / threads / ollama RSS) and clutter the operator-facing view.
_CONSOLE_HIDDEN_MARKERS: tuple[str, ...] = ("[resources]",)

_RUN_LOG = "run.log"  # the run directory's log file the console tails


def is_visible_log_line(line: str) -> bool:
    return not any(marker in line for marker in _CONSOLE_HIDDEN_MARKERS)


def resolve_run_dir(provider, job_id: str) -> tuple[Path | None, int]:
    """Return (run_dir, status_hint). status_hint is 0 on success, HTTP code on error.

    404 when *provider* cannot map jobs to run directories, 410 when the
    job's run directory is unknown or gone.
    """
    if provider is None or not hasattr(provider, "get_log_run_dir"):
        return None, HTTPStatus.NOT_FOUND
    run_dir = provider.get_log_run_dir(job_id)
    if run_dir is None or not run_dir.is_dir():
        return None, HTTPStatus.GONE
    return run_dir, 0


def resolve_run_log(provider, job_id: str) -> tuple[Path | None, int]:
    """Return (log_path, status_hint). status_hint is 0 on success, HTTP code on error."""
    run_dir, status = resolve_run_dir(provider, job_id)
    if run_dir is None:
        return None, status
    log_path = run_dir / _RUN_LOG
    if not log_path.exists():
        return None, HTTPStatus.NOT_FOUND
    return log_path, 0


def read_tail(
    log_path: Path, since: int, env: Mapping[str, str] | None = None,
) -> tuple[list[str], int]:
    """Read lines starting at byte offset *since*. Returns (lines, next_offset).

    Drops any trailing partial line (without newline); caller polls again.
    *env* overrides the per-poll byte cap lookup and defaults to ``os.environ``.
    """
    with open(log_path, "rb") as fh:
        fh.seek(since)
        raw = fh.read(tail_max_bytes(env))
    text = raw.decode("utf-8", errors="replace")
    if not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return [], since  # no complete line yet
        text = text[: last_nl + 1]
    consumed = len(text.encode("utf-8"))
    lines = [ln for ln in text.splitlines() if is_visible_log_line(ln)]
    return lines, since + consumed


def resolve_stream_log_path(provider, job_id: str) -> Path | None:
    """Re-resolved each tick. A job that started in the "preparing" state (no
    output_project yet) eventually emits the report_path marker; from then on
    get_log_run_dir returns the real run dir and run.log appears.
    """
    run_dir, _ = resolve_run_dir(provider, job_id)
    if run_dir is None:
        return None
    return run_dir / _RUN_LOG


def stream_terminal_state(provider, job_id: str) -> str:
    # In-memory job (internal runs) carries the most up-to-date status
    # before the runner has flushed status.json — prefer it.
    if provider is not None:
        job = provider.in_memory_job(job_id)
        if job is not None and job.status in JOB_FINISHED:
            return job.status
    # Fall back to the on-disk status.json the runner writes on exit.
    path = resolve_stream_log_path(provider, job_id)
    if path is None:
        return JobStatus.DONE
    run_dir = path.parent
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return JobStatus.DONE
    data = read_run_status_json(run_dir)
    state = data.get("state") if isinstance(data, dict) else None
    if isinstance(state, str):
        return state
    _logger.debug("status.json unreadable for job %s, reporting done", job_id)
    return JobStatus.DONE
