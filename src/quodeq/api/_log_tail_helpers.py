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


def is_preparing_job(provider, job_id: str) -> bool:
    """Return True if *job_id* refers to a job that may still produce output.

    Used by the SSE routes to keep the EventSource alive while a runner is
    in the "preparing" phase — resolving inputs, cloning a remote repo,
    creating the run directory — but hasn't yet emitted the ``report_path``
    marker that lets the dashboard locate the run directory. A non-200
    answer in that window closes the browser's EventSource for good (the
    spec forbids a retry), which left the Evaluate screen without live
    findings for the whole run.

    Returns False for unknown ids so a typo or a stale jobId from the
    client doesn't keep a connection (and a polling Python thread) open
    forever.
    """
    if provider is None:
        return False
    # Internal job: must be in the in-memory store with a non-terminal
    # status. Pre-marker, ``output_project`` is None so ``get_log_run_dir``
    # returns None — without this check the route would 404 the moment the
    # frontend opens the stream after Start.
    in_memory_job = getattr(provider, "in_memory_job", None)
    job = in_memory_job(job_id) if callable(in_memory_job) else None
    if job is not None and job.status not in JOB_FINISHED:
        return True
    # External job: the CLI creates the run directory before opening the
    # ``run.log`` writer, so there is a brief window where the directory
    # exists but the file does not. If the provider can resolve a real
    # run_dir, treat the run as live.
    if hasattr(provider, "get_log_run_dir"):
        run_dir = provider.get_log_run_dir(job_id)
        if run_dir is not None and run_dir.is_dir():
            return True
    return False


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
    # Cut on the raw bytes: re-encoding the lossy-decoded text would count
    # each invalid byte as three and skip past the next lines.
    last_nl = raw.rfind(b"\n")
    if last_nl == -1:
        return [], since  # no complete line yet
    raw = raw[: last_nl + 1]
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if is_visible_log_line(ln)]
    return lines, since + len(raw)


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
