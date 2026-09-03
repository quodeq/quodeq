"""Dashboard runner — entry point that resolves paths, launches the action API, and serves.

Sub-modules:
- _networking: host/port utilities
- _process: PID tracking, stale-process cleanup
- _server: API startup and serve-and-wait loop
"""
from __future__ import annotations

import logging
import os
import sys

from quodeq.dashboard._api_health import ApiConfig
from quodeq.dashboard._config import BuildConfig, DashboardConfig, ServerConfig
from quodeq.dashboard._networking import _choose_ui_port, _is_port_open
from quodeq.dashboard._probes import ApiProbes, DashboardHooks
from quodeq.dashboard import _server as _server_mod
from quodeq.dashboard._server import (
    _ensure_action_api,
    _ensure_action_api_forced,
)
from quodeq.shared.config_loader import get_default_host as _get_default_host
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.paths import resolve_path

__all__ = [
    "BuildConfig",
    "DashboardConfig",
    "ServerConfig",
    "run_dashboard",
    "validate_paths",
]


def validate_paths(config: DashboardConfig) -> None:
    """Verify that required directories and files exist, creating defaults if needed."""
    if not config.reports_dir.exists():
        if config.reports_defaulted:
            config.reports_dir.mkdir(parents=True, exist_ok=True)
        else:
            raise FileNotFoundError(
                "Reports directory not found. "
                "Run `mkdir -p <path>` or omit --evaluations to use the default."
            )
    if not (config.static_dist / "index.html").exists():
        raise FileNotFoundError("Static dist missing index.html. Run without --no-build to build.")


def _resolve_paths_and_build(
    config: DashboardConfig, *, hooks: DashboardHooks | None = None,
) -> DashboardConfig:
    """Resolve paths, check prerequisites, build UI if needed, choose a free port."""
    hooks = hooks or DashboardHooks()
    reports_dir = resolve_path(str(config.reports_dir))
    repo_root = resolve_path(str(config.repo_root))

    chosen_port = _choose_ui_port(config.server.port)
    if chosen_port != config.server.port:
        log_warning(f"Port {config.server.port} is in use. Using {chosen_port} instead.")

    if config.build.dev:
        hooks.check_prereqs()
        static_dist = hooks.build_ui(config.build.no_build, config.build.reinstall, dev=True)
    elif not config.static_dist_defaulted:
        user_provided_dist = resolve_path(str(config.static_dist))
        if (user_provided_dist / "index.html").exists():
            static_dist = user_provided_dist
        else:
            static_dist = hooks.build_ui(config.build.no_build, config.build.reinstall)
    else:
        static_dist = hooks.build_ui(config.build.no_build, config.build.reinstall)

    return DashboardConfig(
        server=ServerConfig(
            port=chosen_port,
            api_host=config.server.api_host,
            api_port=config.server.api_port,
            api_forced=config.server.api_forced,
        ),
        build=config.build,
        reports_dir=reports_dir,
        static_dist=static_dist,
        repo_root=repo_root,
        reports_defaulted=config.reports_defaulted,
    )


def _start_action_api(
    config: DashboardConfig,
    action_api_host: str,
    action_api_port: int,
    api_config: ApiConfig,
    *,
    probes: ApiProbes | None = None,
    hooks: DashboardHooks | None = None,
) -> tuple[str, "subprocess.Popen | None"]:
    """Resolve and start the action API, returning (url, process).

    Handles both forced-port and auto-scan modes, including killing stale
    processes when not in forced mode.
    """
    hooks = hooks or DashboardHooks()
    if config.server.api_forced:
        return _ensure_action_api_forced(
            action_api_host, action_api_port, static_dist=api_config.static_dist,
            evaluations_dir=api_config.evaluations_dir, probes=probes,
        )
    hooks.kill_stale(action_api_host, action_api_port)
    return _ensure_action_api(
        action_api_host, action_api_port, api_config=api_config, probes=probes,
    )


def _handed_off_to_running_instance(config: DashboardConfig) -> bool:
    """Give a relaunch to the window that is already open. True if handled.

    Checked before the API starts, which is the only order that works: the
    launch used to spawn a second backend, notice the running instance, and
    terminate that backend on the way out — so the running window was competing
    with a launch that had already killed a server on its behalf. Nothing is
    spawned and no PID file is rewritten when this returns True.

    Runs after the UI build so a ``--dev`` relaunch still rebuilds, and the
    focused window reloads into the fresh bundle it serves.
    """
    if not (config.build.use_native and config.build.open_browser):
        return False  # --browser / --no-open have no window to hand off to
    from quodeq.dashboard._instance import InstanceController

    instance = InstanceController()
    if not instance.probe_existing():
        return False
    try:
        instance.send_focus()
    except (ConnectionRefusedError, OSError):
        log_warning("Could not reach the running instance — starting a new one")
        return False
    log_info("quodeq is already running — brought its window to the front.")
    return True


def _maybe_spawn_menubar() -> None:
    """Launch the menu bar icon when the preference is on. Fail-soft.

    Only a real dashboard launch calls this; direct --_api invocations and
    the Settings toggle (PUT /api/menubar) have their own paths.
    """
    try:
        from quodeq.menubar import control, state

        if control.is_supported() and state.is_enabled():
            control.spawn()
    except Exception:
        logging.getLogger(__name__).debug("menubar spawn skipped", exc_info=True)


def _prepare_frozen_macos_launch() -> bool:
    """Packaged-app housekeeping before anything spawns. Fail-silent.

    Cleans staging leftovers from an interrupted self-update, then offers the
    move-to-Applications prompt when running from the DMG or a translocated
    path. True means the app relaunched from /Applications: exit this process.
    """
    if not (getattr(sys, "frozen", False) and sys.platform == "darwin"):
        return False
    try:
        from quodeq.update import first_launch, selfupdate

        selfupdate.cleanup_stale_staging()
        return first_launch.offer_move_to_applications()
    except Exception:  # pragma: no cover - defensive
        return False


def _kick_update_check() -> None:
    """Fire a throttled, non-blocking update check. Fail-silent — never delays launch."""
    try:
        from quodeq.update.checker import check_async

        check_async()
    except Exception:  # pragma: no cover - defensive
        pass


def run_dashboard(
    config: DashboardConfig,
    env: dict[str, str] | None = None,
    *,
    probes: ApiProbes | None = None,
    hooks: DashboardHooks | None = None,
) -> int:
    """Start the dashboard: resolve paths, launch the action API, and serve until exit.

    *env* overrides ``os.environ`` when provided (useful for testing).
    *probes* and *hooks* are injection seams for tests: each defaults to the
    production collaborators of the same name (see ``dashboard/_probes.py``).
    """
    hooks = hooks or DashboardHooks()
    config = _resolve_paths_and_build(config, hooks=hooks)
    validate_paths(config)

    if env is not None:
        environ = env.copy()
    else:
        environ = os.environ
    if config.build.verbose:
        environ["QUODEQ_VERBOSE"] = "1"

    if _prepare_frozen_macos_launch():
        return 0

    if _handed_off_to_running_instance(config):
        return 0

    log_info("Starting dashboard...")
    log_info(f"Reports: {config.reports_dir}")
    log_info(f"Static:  {config.static_dist}")
    log_info(f"Port:    {config.server.port}")

    action_api_host = config.server.api_host or _get_default_host()
    action_api_port = config.server.api_port or config.server.port
    api_config = ApiConfig(static_dist=config.static_dist, evaluations_dir=str(config.reports_dir))
    ensure_api = hooks.ensure_api or _start_action_api
    action_api_url, action_api_process = ensure_api(
        config, action_api_host, action_api_port, api_config, probes=probes, hooks=hooks,
    )

    _kick_update_check()
    _maybe_spawn_menubar()

    _server_mod.serve_and_wait(action_api_url, action_api_process, config)
    return 0
