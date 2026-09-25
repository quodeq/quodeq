"""The current time as the ISO-8601 UTC string stored on jobs, runs and records.

Every timestamp the services layer stamps (job start/end, onboarding
completion, deletion time, scan time) is ``datetime.now(timezone.utc)
.isoformat()``: microsecond precision with a ``+00:00`` offset. The run
state files, the run index and the result cache stamp at second precision
instead (``timespec=ISO_SECONDS``). One home so neither format can drift
between writers.
"""
from __future__ import annotations

from datetime import datetime, timezone

ISO_SECONDS = "seconds"  # isoformat timespec for the second-precision stamps
_ISO_AUTO = "auto"  # isoformat's own default: microseconds unless they are zero


def utc_now_iso(*, timespec: str = _ISO_AUTO) -> str:
    """The current UTC time as an ISO-8601 string with a ``+00:00`` offset."""
    return datetime.now(timezone.utc).isoformat(timespec=timespec)


def utc_iso_from_epoch(epoch_s: float) -> str:
    """*epoch_s* (a POSIX timestamp, e.g. a file mtime) as a second-precision UTC ISO-8601 string."""
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).isoformat(timespec=ISO_SECONDS)
