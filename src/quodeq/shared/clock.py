"""The current time as the ISO-8601 UTC string stored on jobs, runs and records.

Every timestamp the services layer stamps (job start/end, onboarding
completion, deletion time, scan time) is ``datetime.now(timezone.utc)
.isoformat()``: microsecond precision with a ``+00:00`` offset. One home so
the stored format cannot drift between writers.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """The current UTC time as an ISO-8601 string with a ``+00:00`` offset."""
    return datetime.now(timezone.utc).isoformat()
