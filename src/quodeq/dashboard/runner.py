"""Dashboard runner — entry point that resolves paths, launches the action API, and serves.

Sub-modules:
- _networking: host/port utilities
- _process: PID tracking, stale-process cleanup
- _server: API startup and serve-and-wait loop
"""
from __future__ import annotations

from quodeq.dashboard._api_health import ApiConfig
from quodeq.dashboard._build import maybe_build_ui
from quodeq.dashboard._config import BuildConfig, DashboardConfig, ServerConfig
from quodeq.dashboard._networking import _choose_ui_port, _is_port_open
from quodeq.dashboard._process import _kill_stale_action_api
from quodeq.dashboard._server import (
    _ensure_action_api,
    _ensure_action_api_forced,
    _serve_and_wait,
)
from quodeq.shared.config_loader import get_default_host as _get_default_host
from quodeq.shared.logging import log_info, log_warning
from quodeq.shared.paths import resolve_path
from quodeq.shared.prereqs import check_dashboard_prereqs

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


def _resolve_paths_and_build(config: DashboardConfig) -> DashboardConfig:
    """Resolve paths, check prerequisites, build UI if needed, choose a free port."""
    reports_dir = resolve_path(str(config.reports_dir))
    repo_root = resolve_path(str(config.repo_root))

    chosen_port = _choose_ui_port(config.server.port)
    if chosen_port != config.server.port:
        log_warning(f"Port {config.server.port} is in use. Using {chosen_port} instead.")

    if config.build.dev:
        check_dashboard_prereqs()
        static_dist = maybe_build_ui(config.build.no_build, config.build.reinstall, dev=True)
    else:
        user_provided_dist = resolve_path(str(config.static_dist))
        if (user_provided_dist / "index.html").exists():
            static_dist = user_provided_dist
        else:
            if not config.build.no_build:
                check_dashboard_prereqs()
            static_dist = maybe_build_ui(config.build.no_build, config.build.reinstall)

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
) -> tuple[str, "subprocess.Popen | None"]:
    """Resolve and start the action API, returning (url, process).

    Handles both forced-port and auto-scan modes, including killing stale
    processes when not in forced mode.
    """
    if config.server.api_forced:
        return _ensure_action_api_forced(
            action_api_host, action_api_port, static_dist=api_config.static_dist,
            evaluations_dir=api_config.evaluations_dir,
        )
    _kill_stale_action_api(action_api_host, action_api_port)
    return _ensure_action_api(
        action_api_host, action_api_port, api_config=api_config,
    )


def run_dashboard(config: DashboardConfig, env: dict[str, str] | None = None) -> int:
    """Start the dashboard: resolve paths, launch the action API, and serve until exit.

    *env* overrides ``os.environ`` when provided (useful for testing).
    """
    config = _resolve_paths_and_build(config)
    validate_paths(config)

    log_info("Starting dashboard...")
    log_info(f"Reports: {config.reports_dir}")
    log_info(f"Static:  {config.static_dist}")
    log_info(f"Port:    {config.server.port}")

    action_api_host = config.server.api_host or _get_default_host()
    action_api_port = config.server.api_port or config.server.port
    api_config = ApiConfig(static_dist=config.static_dist, evaluations_dir=str(config.reports_dir))
    action_api_url, action_api_process = _start_action_api(config, action_api_host, action_api_port, api_config)

    _serve_and_wait(action_api_url, action_api_process, config)
    return 0
