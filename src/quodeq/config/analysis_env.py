"""Environment-based configuration for the analysis pipeline.

``quodeq.analysis`` never reads the environment; overrides are resolved
here, lazily per call, and passed in.
"""
from __future__ import annotations

import os

from quodeq.shared._env import _env_int


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


def max_output_tokens_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_MAX_OUTPUT_TOKENS override, or None when unset/malformed.

    The business rule (explicit config wins, cloud calls stay uncapped,
    0 disables the local cap) stays with the caller; this only resolves the
    raw override. Digit-parse only: negatives and blanks read as unset.
    """
    raw = (env or os.environ).get("QUODEQ_MAX_OUTPUT_TOKENS", "").strip()
    return int(raw) if raw.isdigit() else None


def api_read_timeout_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_API_READ_TIMEOUT override (whole seconds), or None.

    The business rule (positive values override the read budget outright)
    stays with the caller; this only resolves the raw override. Digit-parse
    only: negatives and blanks read as unset.
    """
    raw = (env or os.environ).get("QUODEQ_API_READ_TIMEOUT", "").strip()
    return int(raw) if raw.isdigit() else None


def context_size_override(env: dict[str, str] | None = None) -> int | None:
    """Return the QUODEQ_CONTEXT_SIZE override, or None when unset/malformed.

    The business rule (env consulted only when the configured context size
    is unset, positive values forwarded as ``num_ctx``) stays with the
    caller; this only resolves the raw override.
    """
    raw = (env or os.environ).get("QUODEQ_CONTEXT_SIZE", "").strip()
    return int(raw) if raw.isdigit() else None


def default_max_turns(env: dict[str, str] | None = None) -> int:
    """Turn ceiling per agent, resolved per construction (not at import)."""
    return _env_int("QUODEQ_DEFAULT_MAX_TURNS", 200, env=env)


def default_max_duration(env: dict[str, str] | None = None) -> int:
    """Wall-clock ceiling per agent in seconds (30 min), resolved per construction."""
    return _env_int("QUODEQ_DEFAULT_MAX_DURATION", 1800, env=env)
