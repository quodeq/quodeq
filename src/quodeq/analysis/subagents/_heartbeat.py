"""Heartbeat and progress reporting for the subagent pool."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.utils import open_text

_HEARTBEAT_INTERVAL = 10
_SECONDS_PER_MINUTE = 60


@dataclass
class HeartbeatContext:
    """Grouped parameters for heartbeat monitoring."""
    queue_path: Path
    dimension_key: str
    jsonl_path: Path
    lock: threading.Lock


def _count_jsonl_findings(jsonl_path: Path, lock: threading.Lock) -> int:
    """Count non-empty lines in a JSONL file under a lock."""
    try:
        if not jsonl_path.exists():
            return 0
        with lock:
            with open_text(jsonl_path) as f:
                return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def heartbeat_loop(
    stop: threading.Event, finished: dict[str, bool],
    ctx: HeartbeatContext,
) -> None:
    """Emit periodic progress lines for the subagent pool."""
    start = time.monotonic()
    while not stop.wait(_HEARTBEAT_INTERVAL):
        try:
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, _SECONDS_PER_MINUTE)
            total_findings = _count_jsonl_findings(ctx.jsonl_path, ctx.lock)
            remaining, taken = FileQueue(ctx.queue_path).stats()
            total_agents = len(finished)
            active = sum(1 for v in finished.values() if not v)
            log_info(
                f"  [{ctx.dimension_key}] {mins}m{secs:02d}s | "
                f"{active} active ({total_agents} total) | "
                f"{taken} files taken ({remaining} left) | "
                f"{total_findings} findings"
            )
        except (OSError, ValueError, RuntimeError) as exc:
            log_warning(f"Heartbeat error: {exc}")
