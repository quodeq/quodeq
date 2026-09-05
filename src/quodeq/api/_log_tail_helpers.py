"""Log-tailing and log-path-resolution helpers for the log-stream routes.

Raw file I/O and the log-parsing business rules used by
``_log_stream_routes.py`` live here rather than in the routes module, mirroring
the split already used by ``_sse_log_helpers.py`` for the SSE tail generator.
"""
from __future__ import annotations

import json
import os
from http import HTTPStatus
from pathlib import Path

# Lines containing this marker are kept in run.log for forensics but suppressed
# from the dashboard's live console — they're per-minute resource snapshots
# (rss / fds / threads / ollama RSS) and clutter the operator-facing view.
_CONSOLE_HIDDEN_MARKERS: tuple[str, ...] = ("[resources]",)

# Per-poll byte cap: a single tail read will not pull more than this many bytes
# into memory in one shot. The remaining bytes will be served on the next poll.
# Caps a runaway log file from blowing out RAM on read.
_DEFAULT_TAIL_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


def _tail_max_bytes() -> int:
    raw = os.environ.get("QUODEQ_LOG_TAIL_MAX_BYTES")
    if not raw:
        return _DEFAULT_TAIL_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TAIL_MAX_BYTES
    return value if value > 0 else _DEFAULT_TAIL_MAX_BYTES


def _is_visible_log_line(line: str) -> bool:
    return not any(marker in line for marker in _CONSOLE_HIDDEN_MARKERS)


def _resolve_run_log(provider, job_id: str) -> tuple[Path | None, int]:
    """Return (log_path, status_hint). status_hint is 0 on success, HTTP code on error."""
    if provider is None or not hasattr(provider, "get_log_run_dir"):
        return None, HTTPStatus.NOT_FOUND
    run_dir = provider.get_log_run_dir(job_id)
    if run_dir is None or not run_dir.is_dir():
        return None, HTTPStatus.GONE
    log_path = run_dir / "run.log"
    if not log_path.exists():
        return None, HTTPStatus.NOT_FOUND
    return log_path, 0


def _read_tail(log_path: Path, since: int) -> tuple[list[str], int]:
    """Read lines starting at byte offset *since*. Returns (lines, next_offset).

    Drops any trailing partial line (without newline); caller polls again.
    """
    with open(log_path, "rb") as fh:
        fh.seek(since)
        raw = fh.read(_tail_max_bytes())
    text = raw.decode("utf-8", errors="replace")
    if not text.endswith("\n"):
        last_nl = text.rfind("\n")
        if last_nl == -1:
            return [], since  # no complete line yet
        text = text[: last_nl + 1]
    consumed = len(text.encode("utf-8"))
    lines = [ln for ln in text.splitlines() if _is_visible_log_line(ln)]
    return lines, since + consumed


def _resolve_stream_log_path(provider, job_id: str) -> Path | None:
    """Re-resolved each tick. A job that started in the "preparing" state (no
    output_project yet) eventually emits the report_path marker; from then on
    get_log_run_dir returns the real run dir and run.log appears.
    """
    if not hasattr(provider, "get_log_run_dir"):
        return None
    run_dir = provider.get_log_run_dir(job_id)
    if run_dir is None or not run_dir.is_dir():
        return None
    return run_dir / "run.log"


def _stream_terminal_state(provider, job_id: str) -> str:
    # In-memory job (internal runs) carries the most up-to-date status
    # before the runner has flushed status.json — prefer it.
    if provider is not None and hasattr(provider, "_jobs"):
        job = provider._jobs.get_job(job_id)
        if job is not None and job.status in {"done", "failed", "cancelled"}:
            return job.status
    # Fall back to the on-disk status.json the runner writes on exit.
    path = _resolve_stream_log_path(provider, job_id)
    if path is None:
        return "completed"
    status_path = path.parent / "status.json"
    if status_path.exists():
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            state = data.get("state")
            if isinstance(state, str):
                return state
        except (OSError, ValueError):
            pass
    return "completed"
