"""Command-line interface for Quodeq evaluation and dashboard commands.

Heavy evaluation logic lives in ``quodeq._cli_evaluation``; this module
re-exports every public and private name so that existing ``from quodeq.cli
import …`` statements continue to work unchanged.
"""

from __future__ import annotations

import sys
from typing import Callable

from quodeq.cli_parser import build_parser  # noqa: F401 — re-export
from quodeq.config.paths import default_paths, load_env_file
from quodeq.dashboard.cli import main as dashboard_main

# Re-export everything from _cli_evaluation so existing imports
# (including tests doing ``from quodeq.cli import _env_int``) keep working.
from quodeq._cli_evaluation import (  # noqa: F401 — public re-exports
    ResolvedInputs,
    _ENV_MAX_TURNS,
    _ENV_MAX_DURATION,
    _ENV_POOL_BUDGET,
    _build_manifest,
    _build_run_config,
    _cleanup_worktree,
    _create_worktree,
    _env_int,
    _execute_pipeline,
    _filter_manifest_by_scope,
    _no_verify,
    _override_manifest_single_file,
    _resolve_evaluation_inputs,
    _resolve_language,
    _resolve_repo,
    _resolve_scope,
    _resolve_single_file,
    _run_pipeline_with_cleanup,
    _save_manifest,
    _setup_run_dirs,
    _subagent_model,
    run_evaluate,
)


_COMMAND_HANDLERS: dict[str, Callable] = {
    "dashboard": lambda argv: dashboard_main(argv[1:] if argv is not None else sys.argv[2:]),
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate subcommand handler."""
    load_env_file(default_paths())
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    command = getattr(args, "handler_command", None) or args.command
    # Default to dashboard when no subcommand is given
    if command is None:
        return dashboard_main(argv[1:] if argv is not None else sys.argv[1:])
    if command == "evaluate":
        return run_evaluate(args)
    if command == "ci":
        from quodeq.ci.cli import handle_ci
        return handle_ci(args)
    if command == "check":
        from quodeq.ci.check import handle_check
        return handle_check(args)
    handler = _COMMAND_HANDLERS.get(command)
    if handler:
        return handler(argv)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
