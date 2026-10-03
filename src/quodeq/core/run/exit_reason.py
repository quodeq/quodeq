"""Why a run or a dimension stopped (pure; written to status.json and dimensions.json)."""
from __future__ import annotations

from enum import StrEnum


class ExitReason(StrEnum):
    """Why a run or a dimension stopped, as persisted alongside its state."""

    DONE = "done"
    TIME_LIMIT = "time_limit"
    DEADLINE = "deadline"
    FAILURE_STREAK = "failure_streak"
    CANCELLED = "cancelled"
    ERROR = "error"
    STALE_DETECTED = "stale_detected"
    STALE_LEGACY_PID_DEAD = "stale_legacy_pid_dead"
    STALE_LEGACY_NO_PID = "stale_legacy_no_pid"


# A run that stopped because its budget ran out, as opposed to failing.
DEADLINE_EXIT_REASONS: frozenset[ExitReason] = frozenset({ExitReason.DEADLINE, ExitReason.TIME_LIMIT})
