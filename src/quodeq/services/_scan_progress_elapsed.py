"""Per-dimension elapsed-time computation for live scan progress.

Split from ``scan_progress.py`` to keep that file under the size ratchet's
300-line cap. Moved verbatim.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from quodeq.services._wiring import file_mtime, latest_dim_activity_mtime, read_queue_state


def _parse_iso_utc(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Legacy status files can carry naive timestamps; subtracting one from an
    # aware now() raises TypeError. Treat naive as UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_started_at(status: dict) -> datetime | None:
    return _parse_iso_utc(status.get("started_at"))


def _queue_take_timestamps(qstate: dict) -> list[float]:
    """Extract valid take-log timestamps from a queue state dict."""
    taken = qstate.get("taken")
    if not isinstance(taken, list):
        return []
    return [
        e["ts"] for e in taken
        if isinstance(e, dict) and isinstance(e.get("ts"), (int, float))
    ]


def _stamped_elapsed_s(record: dict | None, state: str) -> float | None:
    """Per-dim elapsed from the transition timestamps in dimensions.json.

    write_dim_state stamps ``started_at`` when the dimension starts and
    ``completed_at`` / ``interrupted_at`` when it stops, so the duration is a
    subtraction of two explicit values — no file-system forensics. None when
    the record lacks the needed stamps (legacy runs, hard kills that never
    reached the terminal write): the caller falls back to reconstruction.
    """
    if not isinstance(record, dict):
        return None
    start = _parse_iso_utc(record.get("started_at"))
    if start is None:
        return None
    if state == "running":
        return max(0.0, (datetime.now(timezone.utc) - start).total_seconds())
    end = _parse_iso_utc(record.get("completed_at")) or _parse_iso_utc(record.get("interrupted_at"))
    if end is None:
        return None
    return max(0.0, (end - start).total_seconds())


def _dim_elapsed_s(dim_id: str, run_dir: Path, state: str, record: dict | None = None) -> float | None:
    """Per-dim elapsed time.

    Prefers the transition timestamps stamped in dimensions.json (see
    _stamped_elapsed_s). The queue-state reconstruction below remains as a
    fallback for run dirs written before those stamps were preserved,
    external runs from older CLI versions, the consolidated pseudo-dim
    (which has no dimensions.json entry), and dims that died without a
    terminal transition.

    Reconstruction notes: the queue file is atomically rewritten on every
    take (new inode, fresh mtime), so its mtime tracks the *last* take, not
    the dim start — using it as the start made the running clock reset
    toward zero on every take. Start comes from the queue's ``created_at``
    (stamped at init), falling back to the earliest take timestamp, then the
    file mtime for legacy queues. For done dims the end is the latest
    activity signal we still have: last take, evidence-file mtime, or any
    surviving agent streams (streams are deleted at dim completion, so they
    rarely survive).
    """
    if state == "pending":
        return None
    stamped = _stamped_elapsed_s(record, state)
    if stamped is not None:
        return stamped
    queue = run_dir / "evidence" / f"{dim_id}_queue.json"
    qstate = read_queue_state(queue)
    if qstate is None:
        return None
    take_ts = _queue_take_timestamps(qstate)
    start = qstate.get("created_at")
    if not isinstance(start, (int, float)):
        if take_ts:
            start = min(take_ts)
        else:
            mtime = file_mtime(queue)
            if mtime is None:
                return None
            start = mtime
    if state == "running":
        return max(0.0, time.time() - start)
    # done: latest activity signal still on disk
    end = start
    if take_ts:
        end = max(end, max(take_ts))
    activity = latest_dim_activity_mtime(run_dir / "evidence", dim_id)
    if activity is not None:
        end = max(end, activity)
    return max(0.0, end - start)
