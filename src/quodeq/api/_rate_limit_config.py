"""Rate-limit configuration constants and environment helpers."""
from __future__ import annotations

import os

_DEFAULT_RATE_LIMIT_WINDOW = 60
# 60/min was too tight for the dashboard's bulk-dismiss UX — burst-dismissing
# 60+ findings in a minute (a normal user flow on a large project) hit the
# cap, returned 429, and the frontend rolled back its optimistic update so
# violations appeared to "come back". A 10× bump still bounds runaway clients
# but absorbs realistic UI bursts. Hardened deployments can tighten this via
# QUODEQ_RATE_LIMIT_MAX.
_DEFAULT_RATE_LIMIT_MAX = 600
_RATE_STORE_MAX_IPS = 10_000  # max tracked IPs to prevent unbounded memory growth
_PRUNE_THRESHOLD_MULTIPLIER = 2  # prune per-IP list when it exceeds max_requests * this


def _rate_limit_window(env: dict[str, str] | None = None) -> int:
    """Return the rate-limit window in seconds."""
    try:
        return int((env or os.environ).get("QUODEQ_RATE_LIMIT_WINDOW", str(_DEFAULT_RATE_LIMIT_WINDOW)))
    except (ValueError, TypeError):
        return _DEFAULT_RATE_LIMIT_WINDOW


def _rate_limit_max(env: dict[str, str] | None = None) -> int:
    """Return the maximum number of requests per window."""
    try:
        return int((env or os.environ).get("QUODEQ_RATE_LIMIT_MAX", str(_DEFAULT_RATE_LIMIT_MAX)))
    except (ValueError, TypeError):
        return _DEFAULT_RATE_LIMIT_MAX
