"""Environment-based configuration for the analysis pipeline.

``quodeq.analysis`` never reads the environment; overrides are resolved
here, lazily per call, and passed in.
"""
from __future__ import annotations

import os


def failure_streak_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_FAILURE_STREAK override, or None when unset/malformed.

    The business rule (override wins over the configured
    ``failure_streak_threshold``, 0 disables the breaker, negative values
    clamp to 0) stays with the caller; this only resolves the raw override.
    """
    raw = (env or os.environ).get("QUODEQ_FAILURE_STREAK")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
