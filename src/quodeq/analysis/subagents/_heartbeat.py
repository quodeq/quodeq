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
    # Optional fingerprint params — when set, fingerprint is updated each tick
    src: Path | None = None
    all_files: list[str] | None = None
    evidence_dir: Path | None = None
    standards_dir: Path | None = None


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


def _count_jsonl_findings(jsonl_path: Path, lock: threading.Lock) -> FindingCounts:
    """Count total, violation, and compliance lines in a JSONL file under a lock."""
    if not jsonl_path.exists():
        return FindingCounts()
    try:
        with lock:
            return _read_findings_from_file(jsonl_path)
    except OSError:
        return FindingCounts()


def _update_fingerprint(ctx: HeartbeatContext) -> None:
    """Save an incremental fingerprint with all source file hashes."""
    if not ctx.src or not ctx.all_files or not ctx.evidence_dir:
        return
    try:
        from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint
        fp = build_fingerprint(ctx.src, ctx.all_files, ctx.dimension_key, ctx.standards_dir)
        save_fingerprint(fp, ctx.evidence_dir)
    except (OSError, ValueError):
        pass


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
            counts = _count_jsonl_findings(ctx.jsonl_path, ctx.lock)
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
            _update_fingerprint(ctx)
        except (OSError, ValueError, RuntimeError) as exc:
            log_warning(f"Heartbeat error: {exc}")
