"""Environment-based configuration for git clone operations.

``quodeq.services._fs_clone`` never reads the environment; the clone
timeout and shallow-clone lookback window are resolved here, lazily per
call, and passed in.
"""
from __future__ import annotations

from quodeq.shared.env import env_int

# One month of slack over the default git churn lookback (git_lookback_months,
# 3) so the boundary commit is never cut off.
_DEFAULT_SHALLOW_MONTHS = 4

_GIT_CLONE_TIMEOUT_DEFAULT_S = 300  # QUODEQ_GIT_CLONE_TIMEOUT_S fallback


def git_clone_timeout_s(env: dict[str, str] | None = None) -> int:
    """Return the git clone subprocess timeout in seconds.

    Honors QUODEQ_GIT_CLONE_TIMEOUT_S; malformed or sub-1 values fall back
    to the default (300).
    """
    return env_int("QUODEQ_GIT_CLONE_TIMEOUT_S", _GIT_CLONE_TIMEOUT_DEFAULT_S, minimum=1, env=env)


def clone_shallow_months(env: dict[str, str] | None = None) -> int:
    """Return the shallow-clone lookback window, in months.

    Honors QUODEQ_CLONE_SHALLOW_MONTHS; raise it when a project configures a
    larger git churn lookback, or set to 0 to force full-history clones.
    Malformed values fall back to the default (4).
    """
    return env_int("QUODEQ_CLONE_SHALLOW_MONTHS", _DEFAULT_SHALLOW_MONTHS, env=env, warn=False)
