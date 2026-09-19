"""Environment and argv helpers shared by the evaluate CLI modules.

A leaf: ``_cli_evaluation`` re-exports every name here (and ``quodeq.cli``
in turn), and ``_cli_lifecycle`` imports ``_resolve_time_limit`` directly.
"""

from __future__ import annotations

import argparse
import os
import sys

_ENV_MAX_TURNS = "QUODEQ_MAX_TURNS"
_ENV_MAX_DURATION = "QUODEQ_MAX_DURATION"
_ENV_POOL_BUDGET = "QUODEQ_POOL_BUDGET"
_ENV_TIME_LIMIT = "QUODEQ_TIME_LIMIT"


def _resolve_time_limit(args: argparse.Namespace, env: dict[str, str] | None = None) -> int | None:
    """Resolve the run-level time limit from CLI args or env.

    Precedence: explicit CLI flag > QUODEQ_TIME_LIMIT > legacy QUODEQ_POOL_BUDGET.
    Emits a one-line deprecation warning when the legacy CLI flag or env var is
    the source of the value.
    """
    src_env = env or os.environ
    if getattr(args, "pool_budget", None) is not None:
        # argparse stores both --time-limit and --pool-budget on the same dest;
        # detect deprecated form by scanning the original argv.
        if any(a == "--pool-budget" or a.startswith("--pool-budget=") for a in sys.argv[1:]):
            sys.stderr.write(
                "warning: --pool-budget is deprecated, use --time-limit instead\n"
            )
        return args.pool_budget
    if src_env.get(_ENV_TIME_LIMIT) is not None:
        return _env_int(_ENV_TIME_LIMIT, None, env=env)
    if src_env.get(_ENV_POOL_BUDGET) is not None:
        sys.stderr.write(
            f"warning: {_ENV_POOL_BUDGET} is deprecated, use {_ENV_TIME_LIMIT} instead\n"
        )
        return _env_int(_ENV_POOL_BUDGET, None, env=env)
    return None


def _env_int(var: str, default: int | None, env: dict[str, str] | None = None) -> int | None:
    """Read an environment variable as an int, returning *default* if unset or invalid."""
    raw = (env or os.environ).get(var)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override from the environment, or None."""
    return (env or os.environ).get("SUBAGENT_MODEL") or None


def _no_verify(args: argparse.Namespace, env: dict[str, str] | None = None) -> bool:
    """Return True if verification should be skipped (CLI flag or env var)."""
    return args.no_verify or (env or os.environ).get("QUODEQ_NO_VERIFY") == "1"


# Public spellings of the names ``quodeq.cli`` re-exports. The underscore
# originals stay importable from here for in-package callers.
ENV_MAX_TURNS = _ENV_MAX_TURNS
ENV_MAX_DURATION = _ENV_MAX_DURATION
ENV_POOL_BUDGET = _ENV_POOL_BUDGET
env_int = _env_int
no_verify = _no_verify
subagent_model = _subagent_model
