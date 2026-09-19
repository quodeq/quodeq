"""Command-line interface for Quodeq evaluation and dashboard commands.

Heavy evaluation logic lives in ``quodeq._cli_evaluation`` and its siblings;
this module re-exports their entry points under public spellings, so
``from quodeq.cli import …`` never has to name an underscore. The underscore
originals are still importable from the module that defines them.
"""

from __future__ import annotations

import logging
import sys
from typing import Callable

from quodeq.cli_parser import build_parser  # re-export
from quodeq.update.checker import check_async, get_status, set_settings
from quodeq.config.paths import default_paths, load_env_file
from quodeq.dashboard.cli import main as dashboard_main

# Re-export the evaluation entry points under their public spellings. The
# underscore originals stay importable from the module that owns them.
from quodeq._cli_env import (  # noqa: F401 — public re-exports
    ENV_MAX_DURATION,
    ENV_MAX_TURNS,
    ENV_POOL_BUDGET,
    env_int,
    no_verify,
    subagent_model,
)
from quodeq._cli_resolution import (  # noqa: F401 — public re-exports
    ResolvedInputs,
    build_cli_manifest,
    cleanup_worktree,
    create_worktree,
    filter_manifest_by_scope,
    override_manifest_single_file,
    resolve_evaluation_inputs,
    resolve_language,
    resolve_repo,
    resolve_scope,
    resolve_single_file,
)
from quodeq._cli_evaluation import (  # noqa: F401 — public re-exports
    build_run_config,
    execute_pipeline,
    run_evaluate,
    run_pipeline_with_cleanup,
    save_manifest,
    setup_run_dirs,
)

_logger = logging.getLogger(__name__)


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
        _logger.debug("update notice failed", exc_info=True)


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
            except OSError as exc:
                _logger.debug(
                    "could not redirect stdio to devnull after BrokenPipeError: %s", exc)
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
    elif command == "export":
        from quodeq.ci.export_cli import handle_export
        code = handle_export(args)
    else:
        handler = _COMMAND_HANDLERS.get(command)
        code = handler(argv) if handler else 1

    maybe_emit_cli_notice()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
