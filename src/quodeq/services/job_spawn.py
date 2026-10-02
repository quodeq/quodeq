"""Shared start skeleton for the single-slot background sync jobs.

Claim the slot, spawn the worker, and report whether it started. Each job
module keeps its own public result enum and maps this outcome onto it.
"""
from __future__ import annotations

import threading
from enum import StrEnum
from typing import Callable

from quodeq.core.observability import LogSink

Spawn = Callable[[Callable[[], None]], None]


class JobStartOutcome(StrEnum):
    """What ``start_claimed_job`` did."""

    STARTED = "started"
    ALREADY_RUNNING = "already_running"
    FAILED = "failed"  # the worker thread could not be started


def spawn_daemon(target: Callable[[], None]) -> None:
    """Run *target* on a daemon thread."""
    threading.Thread(target=target, daemon=True).start()


def start_claimed_job(
    claimed: bool, target: Callable[[], None], *,
    spawn: Spawn, on_start_failed: Callable[[], None], log: LogSink, label: str,
) -> JobStartOutcome:
    """Spawn *target* when the slot was *claimed*; ``on_start_failed`` records a spawn failure."""
    if not claimed:
        return JobStartOutcome.ALREADY_RUNNING
    try:
        spawn(target)
    except RuntimeError as exc:
        on_start_failed()
        log.error(f"failed to start {label} thread, {exc}")
        return JobStartOutcome.FAILED
    return JobStartOutcome.STARTED
