"""Environment and argv helpers shared by the evaluate CLI modules.

A leaf: ``cli_evaluation`` re-exports every name here (and ``quodeq.cli``
in turn), and ``_cli_lifecycle`` imports ``resolve_time_limit`` directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

from quodeq.shared.constants import ENV_TRUTHY

ENV_MAX_TURNS = "QUODEQ_MAX_TURNS"
ENV_MAX_DURATION = "QUODEQ_MAX_DURATION"
ENV_POOL_BUDGET = "QUODEQ_POOL_BUDGET"
_ENV_TIME_LIMIT = "QUODEQ_TIME_LIMIT"
ENV_NO_CONSOLIDATE = "QUODEQ_NO_CONSOLIDATE"
_POOL_BUDGET_FLAG = "--pool-budget"  # deprecated CLI flag, replaced by --time-limit
_ENV_SUBAGENT_MODEL = "SUBAGENT_MODEL"


def resolve_time_limit(args: argparse.Namespace, env: dict[str, str] | None = None) -> int | None:
    """Resolve the run-level time limit from CLI args or env.

    Precedence: explicit CLI flag > QUODEQ_TIME_LIMIT > legacy QUODEQ_POOL_BUDGET.
    Emits a one-line deprecation warning when the legacy CLI flag or env var is
    the source of the value.
    """
    src_env = cli_environ(env)
    if getattr(args, "pool_budget", None) is not None:
        # argparse stores both --time-limit and --pool-budget on the same dest;
        # detect deprecated form by scanning the original argv.
        if any(a == _POOL_BUDGET_FLAG or a.startswith(f"{_POOL_BUDGET_FLAG}=") for a in sys.argv[1:]):
            sys.stderr.write(
                "warning: --pool-budget is deprecated, use --time-limit instead\n"
            )
        return args.pool_budget
    if src_env.get(_ENV_TIME_LIMIT) is not None:
        return cli_env_int(_ENV_TIME_LIMIT, None, env=env)
    if src_env.get(ENV_POOL_BUDGET) is not None:
        sys.stderr.write(
            f"warning: {ENV_POOL_BUDGET} is deprecated, use {_ENV_TIME_LIMIT} instead\n"
        )
        return cli_env_int(ENV_POOL_BUDGET, None, env=env)
    return None


def cli_env_int(var: str, default: int | None, env: dict[str, str] | None = None) -> int | None:
    """Read an environment variable as an int, returning *default* if unset or invalid.

    The CLI variant: *default* may be None (an unset flag stays unset) and the
    caller, not this function, decides what an absent value means. Distinct from
    ``quodeq.shared.env.env_int``, which always returns an int and warns on a
    malformed value.
    """
    raw = cli_environ(env).get(var)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def subagent_model(env: dict[str, str] | None = None) -> str | None:
    """Return the subagent model override from the environment, or None."""
    return cli_environ(env).get(_ENV_SUBAGENT_MODEL) or None


def cli_environ(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    """The CLI boundary's process-environment seam.

    ``build_run_config`` and the update notice resolve the run's
    environment here, once, and pass the mapping on; the modules they call
    never name ``os.environ`` themselves. The readers in this module go
    through it too, so the module names ``os.environ`` exactly once. An
    injected ``{}`` means "no variables set" and is returned as-is.
    """
    return os.environ if env is None else env


def no_verify(args: argparse.Namespace, env: dict[str, str] | None = None) -> bool:
    """Return True if verification should be skipped (CLI flag or env var)."""
    return args.no_verify or cli_environ(env).get("QUODEQ_NO_VERIFY") == ENV_TRUTHY
