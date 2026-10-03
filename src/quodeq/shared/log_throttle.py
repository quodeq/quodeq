"""Best-effort cooldown for a single repeated log line.

Guards a call site that runs on every request (or otherwise hot path) from
becoming an unbounded log source on its own, while still surfacing the
first occurrence immediately. See ``api/security.py``'s CSP same-origin ws
failure logging for the motivating call site.
"""
from __future__ import annotations


class LogThrottle:
    """Lock-free, best-effort rate limiter for one log call site.

    No lock: a rare double-emit right at the window boundary under
    concurrent callers is harmless here, because this guards a diagnostic
    cooldown, not a correctness invariant.
    """

    def __init__(self, interval_s: float) -> None:
        self._interval_s = interval_s
        # None, not 0.0: *now* is typically time.monotonic() (seconds since
        # boot), so a 0.0 sentinel would silently drop the first emission on
        # any machine up for less than the interval (a desktop app launched
        # at login).
        self._last_emit_at: float | None = None

    def should_emit(self, now: float) -> bool:
        """True if the caller may log now. Records that emission first."""
        if self._last_emit_at is not None and now - self._last_emit_at < self._interval_s:
            return False
        self._last_emit_at = now
        return True
