"""Heartbeat and progress reporting for the subagent pool."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.analysis.subagents.jsonl_utils import FindingTally, tally_unique_findings
from quodeq.shared.logging import log_info, log_warning

_HEARTBEAT_INTERVAL = 10
_SECONDS_PER_MINUTE = 60
_HEARTBEAT_FMT = (
    "[{dimension}] {mins}m{secs:02d}s | "
    "{violations} v · {compliance} c{suppressed} | "
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
    # Predicate over a raw evidence row: True when the dashboard already
    # suppresses that finding. Injected (see quodeq.services.suppression)
    # rather than imported, so this module stays free of a services import.
    suppressed: Callable[[dict], bool] | None = None


def _read_tally(
    jsonl_path: Path, lock: threading.Lock,
    suppressed: Callable[[dict], bool] | None = None,
) -> FindingTally:
    """Tally under the shared write lock to avoid TOCTOU with MCP writers."""
    try:
        with lock:
            return tally_unique_findings(jsonl_path, suppressed=suppressed)
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
    ``ctx.suppressed`` nets out findings the user already dismissed or deleted
    — the scanner keeps re-finding them, and a raw count here would read as
    several times the number the finished report shows. The excluded total is
    appended as its own ``N supp`` segment so the drop is never silent.
    """
    start = time.monotonic()
    while not stop.wait(_HEARTBEAT_INTERVAL):
        try:
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, _SECONDS_PER_MINUTE)
            tally = _read_tally(ctx.jsonl_path, ctx.lock, ctx.suppressed)
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
                suppressed=f" · {tally.suppressed} supp" if tally.suppressed else "",
            ))
        except (OSError, ValueError, RuntimeError) as exc:
            log_warning(f"Heartbeat error: {exc}")
