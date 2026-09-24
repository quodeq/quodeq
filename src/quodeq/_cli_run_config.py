"""Run-config assembly phases for ``cli_evaluation.build_run_config``.

Split out so the orchestrator stays a short list of phase calls: this module
owns the dimension filter, the flag/env-derived caps (``_RunLimits``) and the
``AnalysisOptions`` mapping. ``build_run_config`` itself stays in
``cli_evaluation`` because tests patch ``default_paths`` at that module's path.

Patch target note: the names below are looked up in THIS module's globals, so
tests patch ``quodeq._cli_run_config.<name>`` — ``cli_env_int``, ``no_verify``,
``resolve_time_limit``, ``default_dispatch_policy``,
``expand_dimension_aliases`` and ``AnalysisOptions``. ``cli_evaluation``
re-exports some of the same names for ``quodeq.cli``, but patching them there
does not reach this module.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.analysis.cache.local import default_cache_root
from quodeq.analysis.dimension_aliases import expand_dimension_aliases
from quodeq.analysis.dispatch_policy import DispatchPolicy, default_dispatch_policy
from quodeq.analysis.runner import AnalysisOptions
from quodeq.shared.logging import log_info
from quodeq.shared.utils import get_ai_cmd_path

from quodeq._cli_env import (
    ENV_MAX_DURATION,
    ENV_MAX_TURNS,
    cli_env_int,
    cli_environ,
    no_verify,
    resolve_time_limit,
)

if TYPE_CHECKING:
    # Annotation only — a runtime import would close the cycle, since
    # cli_evaluation imports this module.
    from quodeq.cli_evaluation import RunConfigLocals


@dataclass(frozen=True, slots=True)
class _RunLimits:
    """The caps and switches build_run_config reads off CLI flags and env."""
    max_turns: int | None
    max_duration: int | None
    max_subagents: int | None
    verify_findings: bool
    time_limit: int | None
    incremental: bool
    dry_run: bool
    dispatch_policy: DispatchPolicy
    ai_cmd_path: str | None
    cache_root: Path


def resolve_limits(args: argparse.Namespace, env: dict[str, str] | None = None) -> _RunLimits:
    environ = cli_environ(env)
    return _RunLimits(
        max_turns=args.max_turns if args.max_turns is not None else cli_env_int(ENV_MAX_TURNS, None, env=env),
        max_duration=args.max_duration if args.max_duration is not None else cli_env_int(ENV_MAX_DURATION, None, env=env),
        max_subagents=args.n_subagents,
        verify_findings=not no_verify(args, env=env),
        time_limit=resolve_time_limit(args, env=env),
        incremental=not (getattr(args, "clean_scan", False) or bool(getattr(args, "diff_from", None))),
        dry_run=getattr(args, "dry_run", False),
        dispatch_policy=default_dispatch_policy(env=environ),
        ai_cmd_path=get_ai_cmd_path(environ),
        cache_root=default_cache_root(environ),
    )


def build_analysis_options(
    dimensions_filter: list[str] | None,
    resolved: RunConfigLocals,
    limits: _RunLimits,
) -> AnalysisOptions:
    return AnalysisOptions(
        ai_model=resolved.effective_ai_model,
        dimensions=dimensions_filter,
        max_turns=limits.max_turns,
        max_duration=limits.max_duration,
        max_subagents=limits.max_subagents,
        subagent_model=resolved.subagent_model,
        verify_findings=limits.verify_findings,
        consolidated=resolved.consolidated,
        time_limit=limits.time_limit,
        incremental=limits.incremental,
        incremental_file_filter=resolved.diff_files,
        dry_run=limits.dry_run,
        diff_from=resolved.diff_from,
        skip_scoring=resolved.skip_scoring,
        ai_cmd_path=limits.ai_cmd_path,
        cache_root=limits.cache_root,
    )


def dimensions_filter_for(args: argparse.Namespace) -> list[str] | None:
    expanded_dimensions = expand_dimension_aliases(args.dimensions)
    dimensions_filter = [d.strip() for d in expanded_dimensions.split(",") if d.strip()] if expanded_dimensions else None
    log_info(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all")
    return dimensions_filter
