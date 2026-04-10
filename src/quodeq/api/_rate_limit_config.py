"""Rate-limit configuration constants and environment helpers."""
from __future__ import annotations

import os

_DEFAULT_RATE_LIMIT_WINDOW = 60
_DEFAULT_RATE_LIMIT_MAX = 60
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
