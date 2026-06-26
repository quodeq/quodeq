"""Command-line interface for Quodeq evaluation and dashboard commands.

Heavy evaluation logic lives in ``quodeq._cli_evaluation``; this module
re-exports every public and private name so that existing ``from quodeq.cli
import …`` statements continue to work unchanged.
"""

from __future__ import annotations

import sys
from typing import Callable

from quodeq.cli_parser import build_parser  # noqa: F401 — re-export
from quodeq.update.checker import check_async, get_status, set_settings
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


def maybe_emit_cli_notice(stream=None, env: dict[str, str] | None = None) -> None:
    """Print a one-line update notice (and a one-time disclosure) after a command.

    Interactive terminals only; silent in CI, when opted out, or when piped.
    Fail-silent — never raises. Also kicks a throttled background check so the
    NEXT invocation has fresh data.
    """
    import os

    out = stream if stream is not None else sys.stdout
    environ = env if env is not None else os.environ
    try:
        if not getattr(out, "isatty", lambda: False)():
            return
        if environ.get("QUODEQ_NO_UPDATE_NOTIFIER"):
            return
        if environ.get("CI") or environ.get("CONTINUOUS_INTEGRATION"):
            return
        check_async()
        status = get_status()
        if not status.get("disclosed"):
            print(
                "quodeq checks PyPI/GitHub for updates. Disable with "
                "QUODEQ_NO_UPDATE_NOTIFIER=1 or in Settings.",
                file=out,
            )
            set_settings(disclosed=True)
        if status.get("update_available"):
            tag = "Security update" if status.get("is_security") else "Update available"
            action = status.get("action_command") or "see the releases page"
            print(
                f"{tag}: {status['current']} → {status['latest']}. Run: {action}",
                file=out,
            )
    except Exception:  # pragma: no cover - defensive
        pass


def _install_broken_pipe_guard() -> None:
    """Silently redirect stdout/stderr to /dev/null after a BrokenPipeError.

    When the CLI runs as a subprocess of the dashboard API and the API
    dies (e.g., the user restarted the dashboard mid-scan), the child's
    inherited stdout pipe closes. Subsequent `print()` calls raise
    BrokenPipeError and take down the analysis with `exit_reason:
    exception: BrokenPipeError` even though the scan finished and the
    evidence is already on disk.

    Install a sys.excepthook that, on BrokenPipeError, swaps stdout/
    stderr to os.devnull and swallows the exception so the lifecycle
    context can complete its normal transition to DONE.
    """
    import os as _os  # noqa: PLC0415
    import sys as _sys  # noqa: PLC0415
    previous_hook = _sys.excepthook

    def _hook(exc_type, exc_value, traceback):
        if issubclass(exc_type, BrokenPipeError):
            try:
                devnull = _os.open(_os.devnull, _os.O_WRONLY)
                _os.dup2(devnull, _sys.stdout.fileno())
                _os.dup2(devnull, _sys.stderr.fileno())
            except OSError:
                pass
            return  # swallow
        previous_hook(exc_type, exc_value, traceback)

    _sys.excepthook = _hook


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the appropriate subcommand handler."""
    from quodeq.shared._io import configure_stdio_utf8
    configure_stdio_utf8()
    _install_broken_pipe_guard()
    load_env_file(default_paths())
    parser = build_parser()
    args, remaining = parser.parse_known_args(argv)
    command = getattr(args, "handler_command", None) or args.command
    # Default to dashboard when no subcommand is given — skip the notice (dashboard has its own banner)
    if command is None:
        return dashboard_main(argv[1:] if argv is not None else sys.argv[1:])

    if command == "evaluate":
        code = run_evaluate(args)
    elif command == "ci":
        from quodeq.ci.cli import handle_ci
        code = handle_ci(args)
    elif command == "review":
        from quodeq.ci.review import handle_review
        code = handle_review(args)
    else:
        handler = _COMMAND_HANDLERS.get(command)
        code = handler(argv) if handler else 1

    maybe_emit_cli_notice()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
