"""Heartbeat and progress reporting for the subagent pool."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.jsonl_utils import FindingTally, tally_unique_findings
from quodeq.shared.logging import log_info, log_warning

_HEARTBEAT_INTERVAL = 10
_SECONDS_PER_MINUTE = 60
_HEARTBEAT_FMT = (
    "[{dimension}] {mins}m{secs:02d}s | "
    "{violations} v · {compliance} c | "
    "files {taken}/{total_files} · {remaining} left | "
    "{active} agent{plural}"
)


@dataclass
class HeartbeatContext:
    """Grouped parameters for heartbeat monitoring."""
    queue_path: Path
    dimension_key: str
    jsonl_path: Path
    lock: threading.Lock


def _read_tally(jsonl_path: Path, lock: threading.Lock) -> FindingTally:
    """Tally under the shared write lock to avoid TOCTOU with MCP writers."""
    try:
        with lock:
            return tally_unique_findings(jsonl_path)
    except OSError:
        return FindingTally()


def heartbeat_loop(
    stop: threading.Event, finished: dict[str, bool],
    ctx: HeartbeatContext,
) -> None:
    """Emit periodic progress lines for the subagent pool.

    Each tick re-reads the dimension JSONL and deduplicates by
    ``(p, file, line, t)`` in memory, so the violation/compliance counts
    always match :mod:`quodeq.services.scan_progress` (which the UI consumes).
    """
    start = time.monotonic()
    while not stop.wait(_HEARTBEAT_INTERVAL):
        try:
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, _SECONDS_PER_MINUTE)
            tally = _read_tally(ctx.jsonl_path, ctx.lock)
            remaining, taken = FileQueue(ctx.queue_path).stats()
            active = sum(1 for v in finished.values() if not v)
            log_info(_HEARTBEAT_FMT.format(
                dimension=ctx.dimension_key,
                mins=mins,
                secs=secs,
                active=active,
                plural="" if active == 1 else "s",
                taken=taken,
                total_files=taken + remaining,
                remaining=remaining,
                violations=tally.violations,
                compliance=tally.compliance,
            ))
        except (OSError, ValueError, RuntimeError) as exc:
            log_warning(f"Heartbeat error: {exc}")
