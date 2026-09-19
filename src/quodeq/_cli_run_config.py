"""Run-config assembly phases for ``_cli_evaluation._build_run_config``.

Split out so the orchestrator stays a short list of phase calls: this module
owns the dimension filter, the flag/env-derived caps (``_RunLimits``) and the
``AnalysisOptions`` mapping. ``_build_run_config`` itself stays in
``_cli_evaluation`` because ~15 test files patch its collaborators at that
module's path.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from quodeq.analysis._dimension_aliases import expand_dimension_aliases
from quodeq.analysis.dispatch_policy import DispatchPolicy, default_dispatch_policy
from quodeq.analysis.runner import AnalysisOptions
from quodeq.shared.logging import log_info

from quodeq._cli_env import (
    _ENV_MAX_DURATION,
    _ENV_MAX_TURNS,
    _env_int,
    _no_verify,
    _resolve_time_limit,
)


@dataclass(frozen=True, slots=True)
class _RunLimits:
    """The caps and switches _build_run_config reads off CLI flags and env."""
    max_turns: int | None
    max_duration: int | None
    max_subagents: int | None
    verify_findings: bool
    time_limit: int | None
    incremental: bool
    dry_run: bool
    dispatch_policy: DispatchPolicy


def _resolve_limits(args: argparse.Namespace, env: dict[str, str] | None = None) -> _RunLimits:
    return _RunLimits(
        max_turns=args.max_turns if args.max_turns is not None else _env_int(_ENV_MAX_TURNS, None, env=env),
        max_duration=args.max_duration if args.max_duration is not None else _env_int(_ENV_MAX_DURATION, None, env=env),
        max_subagents=args.n_subagents,
        verify_findings=not _no_verify(args, env=env),
        time_limit=_resolve_time_limit(args, env=env),
        incremental=not (getattr(args, "clean_scan", False) or bool(getattr(args, "diff_from", None))),
        dry_run=getattr(args, "dry_run", False),
        dispatch_policy=default_dispatch_policy(env=env or os.environ),
    )


def _build_analysis_options(
    dimensions_filter: list[str] | None,
    resolved: tuple,
    limits: _RunLimits,
) -> AnalysisOptions:
    (
        consolidated, effective_ai_model, subagent_model_val,
        diff_from, diff_files, skip_scoring,
    ) = resolved
    incremental_file_filter: set[str] | None = diff_files
    return AnalysisOptions(
        ai_model=effective_ai_model,
        dimensions=dimensions_filter,
        max_turns=limits.max_turns,
        max_duration=limits.max_duration,
        max_subagents=limits.max_subagents,
        subagent_model=subagent_model_val,
        verify_findings=limits.verify_findings,
        consolidated=consolidated,
        time_limit=limits.time_limit,
        incremental=limits.incremental,
        incremental_file_filter=incremental_file_filter,
        dry_run=limits.dry_run,
        diff_from=diff_from,
        skip_scoring=skip_scoring,
    )


def _dimensions_filter(args: argparse.Namespace) -> list[str] | None:
    expanded_dimensions = expand_dimension_aliases(args.dimensions)
    dimensions_filter = [d.strip() for d in expanded_dimensions.split(",") if d.strip()] if expanded_dimensions else None
    log_info(f"Dimensions: {', '.join(dimensions_filter)}" if dimensions_filter else "Dimensions: all")
    return dimensions_filter
