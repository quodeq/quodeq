"""Dashboard runner — builds the UI, starts the action API, and serves the dashboard.

Key functions and their contracts:
- validate_paths: verifies required directories/files exist before serving.
- _kill_stale_action_api: terminates a previously-recorded action API process via
  PID file; waits up to _STALE_KILL_DEADLINE_S for the port to free.
- _ensure_action_api: finds a free port, spawns the action API, and waits for it
  to become healthy; returns (base_url, process) or (base_url, None) if already up.
- _ensure_action_api_forced: like _ensure_action_api but uses an exact port; raises
  RuntimeError if the port is occupied by a non-healthy process.
"""
from __future__ import annotations

from pathlib import Path
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser

from quodeq.dashboard._api_health import ApiConfig, action_api_healthy, spawn_and_wait
from quodeq.dashboard._build import maybe_build_ui
from quodeq.dashboard._config import BuildConfig, DashboardConfig, ServerConfig
from quodeq.shared.logging import log_debug, log_info, log_success, log_warning
from quodeq.shared.paths import resolve_path
from quodeq.shared.config_loader import get_default_host as _get_default_host


_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0"})
_IS_WIN32 = sys.platform == "win32"
_MAX_PORT_SCAN_TRIES = 20


def _terminate_pid(pid: int) -> None:
    """Send a termination signal to a process, platform-aware."""
    os.kill(pid, signal.SIGTERM if not _IS_WIN32 else signal.CTRL_BREAK_EVENT)


def _get_pid_file(env: dict[str, str] | None = None) -> Path:
    """Return a PID file path in a user-private runtime directory.

    Override the default location via ``QUODEQ_RUN_DIR``.
    """
    env_run_dir = (env or os.environ).get("QUODEQ_RUN_DIR")
    run_dir = Path(env_run_dir) if env_run_dir else Path.home() / ".quodeq" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "action_api.pid"


_PORT_CHECK_TIMEOUT_S = 2
_POLL_INTERVAL_S = 0.1
_PROCESS_WAIT_TIMEOUT_S = 5
_MAX_PORT = 65535
_STALE_KILL_DEADLINE_S = 3


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


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(_PORT_CHECK_TIMEOUT_S)
        return sock.connect_ex((host, port)) == 0


def _choose_ui_port(start: int, host: str | None = None) -> int:
    host = host if host is not None else _get_default_host()
    port = start
    while _is_port_open(host, port):
        port += 1
        if port > _MAX_PORT:
            raise RuntimeError("No free port available.")
    return port


def _kill_stale_action_api(host: str, port: int) -> None:
    """Kill any lingering action API processes using PID file tracking."""
    pid_file = _get_pid_file()
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            _terminate_pid(pid)
        except (ValueError, OSError) as exc:
            log_debug(f"Could not kill stale action API (pid file): {exc}")
        try:
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            log_debug(f"Could not remove stale PID file: {exc}")
    deadline = time.monotonic() + _STALE_KILL_DEADLINE_S
    while _is_port_open(host, port) and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)


def _spawn_and_wait_local(port: int, base_url: str, api_config: ApiConfig | None = None) -> tuple[str, subprocess.Popen]:
    """Spawn the action API on *port* and wait for it to become healthy."""
    return spawn_and_wait(port, base_url, _get_pid_file(), _get_default_host(), api_config)


def _allow_plaintext_http(override: bool | None = None, env: dict[str, str] | None = None) -> bool:
    """Return True if plaintext HTTP to non-localhost is allowed."""
    if override is not None:
        return override
    return (env or os.environ).get("QUODEQ_ALLOW_PLAINTEXT_HTTP") == "1"


def _ensure_action_api(
    host: str,
    start_port: int,
    max_tries: int = _MAX_PORT_SCAN_TRIES,
    api_config: ApiConfig | None = None,
) -> tuple[str, subprocess.Popen | None]:
    cfg = api_config or ApiConfig()
    if host not in _LOCAL_HOSTS:
        if _allow_plaintext_http(cfg.allow_plaintext):
            import logging
            logging.getLogger(__name__).warning(
                "API traffic to %s uses plaintext HTTP; use a TLS reverse proxy for remote hosts", host,
            )
        else:
            raise RuntimeError(
                f"Plaintext HTTP to non-localhost host {host!r} is not allowed. "
                "Set QUODEQ_ALLOW_PLAINTEXT_HTTP=1 to explicitly opt in, "
                "or use a TLS reverse proxy."
            )
    port = start_port
    for _ in range(max_tries):
        base_url = f"http://{host}:{port}"
        if _is_port_open(host, port):
            if action_api_healthy(base_url):
                return base_url, None
            port += 1
            continue
        return _spawn_and_wait_local(port, base_url, cfg)
    raise RuntimeError("Unable to find a free port for Action API.")


def _ensure_action_api_forced(host: str, port: int, static_dist: Path | None = None, evaluations_dir: str | None = None) -> tuple[str, subprocess.Popen | None]:
    base_url = f"http://{host}:{port}"
    if _is_port_open(host, port):
        if action_api_healthy(base_url):
            return base_url, None
        raise RuntimeError(f"Port {port} on {host} is in use and not a healthy Action API.")
    return _spawn_and_wait_local(port, base_url, ApiConfig(static_dist=static_dist, evaluations_dir=evaluations_dir))


def _resolve_paths_and_build(config: DashboardConfig) -> DashboardConfig:
    """Resolve paths, choose a free port, and run npm build if needed.

    Returns a new DashboardConfig with resolved paths.
    """
    reports_dir = resolve_path(str(config.reports_dir))
    static_dist = resolve_path(str(config.static_dist))
    repo_root = resolve_path(str(config.repo_root))

    chosen_port = _choose_ui_port(config.server.port)
    if chosen_port != config.server.port:
        log_warning(f"Port {config.server.port} is in use. Using {chosen_port} instead.")

    maybe_build_ui(config.build.no_build, config.build.reinstall, static_dist, repo_root)

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


def _wait_for_process(proc: subprocess.Popen) -> None:
    """Block until *proc* terminates, polling every 5 seconds."""
    while proc.poll() is None:
        try:
            proc.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            pass


def _serve_and_wait(action_api_url: str, action_api_process: subprocess.Popen | None, config: DashboardConfig) -> None:
    """Open browser, register signal handlers, and block until exit."""
    log_success(f"Dashboard running at {action_api_url}")

    if config.build.open_browser:
        webbrowser.open(action_api_url)

    def _stop_children() -> None:
        if action_api_process and action_api_process.poll() is None:
            action_api_process.terminate()
            try:
                action_api_process.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                action_api_process.kill()

    def _handle_tstp(_signum, _frame) -> None:
        _stop_children()
        sys.exit(0)

    if hasattr(signal, "SIGTSTP"):
        signal.signal(signal.SIGTSTP, _handle_tstp)

    try:
        if action_api_process:
            _wait_for_process(action_api_process)
        elif _IS_WIN32:
            import threading
            threading.Event().wait()
        else:
            signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_children()


def _start_action_api(
    config: DashboardConfig,
    action_api_host: str,
    action_api_port: int,
    api_config: ApiConfig,
) -> tuple[str, subprocess.Popen | None]:
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


def run_dashboard(config: DashboardConfig) -> int:
    """Start the dashboard: resolve paths, launch the action API, and serve until exit."""
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
