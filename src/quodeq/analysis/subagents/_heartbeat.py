"""Heartbeat and progress reporting for the subagent pool."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from quodeq.analysis.stream.parser import FINDING_TYPE_COMPLIANCE, FINDING_TYPE_VIOLATION
from quodeq.analysis.subagents.file_queue import FileQueue
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.utils import open_text

_HEARTBEAT_INTERVAL = 10
_SECONDS_PER_MINUTE = 60
_HEARTBEAT_FMT = (
    "  [{dimension}] {mins}m{secs:02d}s | "
    "{active} active ({total_agents} total) | "
    "{taken} files taken ({remaining} left) | "
    "{findings} findings | "
    "{violations} violations \u00b7 {compliances} compliance"
)


@dataclass
class HeartbeatContext:
    """Grouped parameters for heartbeat monitoring."""
    queue_path: Path
    dimension_key: str
    jsonl_path: Path
    lock: threading.Lock


@dataclass
class FindingCounts:
    """Aggregated finding counts from a JSONL file."""
    total: int = 0
    violations: int = 0
    compliances: int = 0


def _classify_jsonl_line(line: str, counts: FindingCounts) -> None:
    """Classify a single non-empty JSONL line and update *counts* in place."""
    counts.total += 1
    try:
        entry = json.loads(line)
        t = entry.get("t")
        if t == FINDING_TYPE_VIOLATION:
            counts.violations += 1
        elif t == FINDING_TYPE_COMPLIANCE:
            counts.compliances += 1
    except json.JSONDecodeError:
        pass


def _read_findings_from_file(jsonl_path: Path) -> FindingCounts:
    """Open *jsonl_path* and classify every non-empty line into finding counts.

    Caller is responsible for holding any required lock before invoking this.
    """
    counts = FindingCounts()
    with open_text(jsonl_path) as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            _classify_jsonl_line(stripped, counts)
    return counts


def _count_jsonl_findings_incremental(
    jsonl_path: Path, lock: threading.Lock,
    cumulative: FindingCounts, offset: int,
) -> tuple[FindingCounts, int]:
    """Incrementally count findings from *offset*, updating *cumulative* in place."""
    try:
        with lock:
            if not jsonl_path.exists():
                return cumulative, offset
            with open(jsonl_path, "rb") as f:
                f.seek(offset)
                new_bytes = f.read()
                new_offset = offset + len(new_bytes)
            for line in new_bytes.decode("utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if stripped:
                    _classify_jsonl_line(stripped, cumulative)
            return cumulative, new_offset
    except OSError:
        return cumulative, offset


def _count_jsonl_findings(jsonl_path: Path, lock: threading.Lock) -> FindingCounts:
    """Count total, violation, and compliance lines in a JSONL file under a lock.

    The existence check and read are both inside the lock to avoid a TOCTOU
    race with concurrent MCP writers that may create the file between the
    check and the open.
    """
    try:
        with lock:
            if not jsonl_path.exists():
                return FindingCounts()
            return _read_findings_from_file(jsonl_path)
    except OSError:
        return FindingCounts()


def heartbeat_loop(
    stop: threading.Event, finished: dict[str, bool],
    ctx: HeartbeatContext,
) -> None:
    """Emit periodic progress lines for the subagent pool.

    Tracks JSONL file offset across ticks to avoid re-reading the entire file
    on every heartbeat cycle.
    """
    start = time.monotonic()
    cumulative = FindingCounts()
    jsonl_offset = 0
    while not stop.wait(_HEARTBEAT_INTERVAL):
        try:
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, _SECONDS_PER_MINUTE)
            counts, jsonl_offset = _count_jsonl_findings_incremental(
                ctx.jsonl_path, ctx.lock, cumulative, jsonl_offset,
            )
            remaining, taken = FileQueue(ctx.queue_path).stats()
            total_agents = len(finished)
            active = sum(1 for v in finished.values() if not v)
            log_info(_HEARTBEAT_FMT.format(
                dimension=ctx.dimension_key,
                mins=mins,
                secs=secs,
                active=active,
                total_agents=total_agents,
                taken=taken,
                remaining=remaining,
                findings=counts.total,
                violations=counts.violations,
                compliances=counts.compliances,
            ))
        except (OSError, ValueError, RuntimeError) as exc:
            log_warning(f"Heartbeat error: {exc}")
