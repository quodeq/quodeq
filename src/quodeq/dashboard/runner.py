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
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from quodeq.dashboard._build import maybe_build_ui
from quodeq.dashboard._config import BuildConfig, DashboardConfig, ServerConfig
from quodeq.shared.logging import log_debug, log_info, log_success, log_warning
from quodeq.shared.paths import resolve_path
from quodeq.shared.utils import ACTION_API_MODULE, DEFAULT_HOST


def _get_pid_file() -> Path:
    """Return a PID file path in a user-private runtime directory."""
    run_dir = Path.home() / ".quodeq" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "action_api.pid"


_HEALTH_CHECK_TIMEOUT_S = 0.5
_POLL_INTERVAL_S = 0.1
_HEALTH_POLL_INTERVAL_S = 0.2
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
        return sock.connect_ex((host, port)) == 0


def _choose_ui_port(start: int, host: str = DEFAULT_HOST) -> int:
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
            os.kill(pid, signal.SIGTERM)
        except (ValueError, OSError) as exc:
            log_debug(f"Could not kill stale action API (pid file): {exc}")
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass
    deadline = time.monotonic() + _STALE_KILL_DEADLINE_S
    while _is_port_open(host, port) and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)


def _spawn_action_api(port: int, static_dist: Path | None = None) -> subprocess.Popen:
    env = os.environ.copy()
    env["QUODEQ_ACTION_API_PORT"] = str(port)
    env.setdefault("QUODEQ_ACTION_API_HOST", DEFAULT_HOST)
    if static_dist:
        env["QUODEQ_STATIC_DIST"] = str(static_dist)
    proc = subprocess.Popen(
        [sys.executable, "-m", ACTION_API_MODULE],
        env=env,
        start_new_session=True,
    )
    try:
        _get_pid_file().write_text(str(proc.pid))
    except (OSError, AttributeError) as exc:
        log_warning(f"Could not write PID file: {exc}")
    return proc


def _wait_for_action_api(base_url: str, timeout_s: float = 10) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _action_api_healthy(base_url):
            return None
        time.sleep(_HEALTH_POLL_INTERVAL_S)
    raise TimeoutError(f"Action API did not become ready within {timeout_s} seconds.")


def _action_api_healthy(base_url: str) -> bool:
    url = f"{base_url}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=_HEALTH_CHECK_TIMEOUT_S) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("ok") is True
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def _spawn_and_wait(port: int, base_url: str, static_dist: Path | None = None) -> tuple[str, subprocess.Popen]:
    """Spawn the action API on *port* and wait for it to become healthy."""
    process = _spawn_action_api(port, static_dist=static_dist)
    try:
        _wait_for_action_api(base_url)
    except (subprocess.TimeoutExpired, OSError, TimeoutError):
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    return base_url, process


def _ensure_action_api(host: str, start_port: int, max_tries: int = 20, static_dist: Path | None = None) -> tuple[str, subprocess.Popen | None]:
    port = start_port
    for _ in range(max_tries):
        base_url = f"http://{host}:{port}"
        if _is_port_open(host, port):
            if _action_api_healthy(base_url):
                return base_url, None
            port += 1
            continue
        return _spawn_and_wait(port, base_url, static_dist)
    raise RuntimeError("Unable to find a free port for Action API.")


def _ensure_action_api_forced(host: str, port: int, static_dist: Path | None = None) -> tuple[str, subprocess.Popen | None]:
    base_url = f"http://{host}:{port}"
    if _is_port_open(host, port):
        if _action_api_healthy(base_url):
            return base_url, None
        raise RuntimeError(f"Port {port} on {host} is in use and not a healthy Action API.")
    return _spawn_and_wait(port, base_url, static_dist)


def _resolve_paths_and_build(config: DashboardConfig) -> DashboardConfig:
    """Resolve paths, choose a free port, and run npm build if needed.

    Returns a new DashboardConfig with resolved paths.
    """
    reports_dir = resolve_path(str(config.reports_dir))
    static_dist = resolve_path(str(config.static_dist))
    repo_root = resolve_path(str(config.repo_root))

    chosen_port = _choose_ui_port(config.port)
    if chosen_port != config.port:
        log_warning(f"Port {config.port} is in use. Using {chosen_port} instead.")

    maybe_build_ui(config.no_build, config.reinstall, static_dist, repo_root)

    return DashboardConfig(
        server=ServerConfig(
            port=chosen_port,
            api_host=config.api_host,
            api_port=config.api_port,
            api_forced=config.api_forced,
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
            log_debug("Process still running, continuing to wait...")


def _serve_and_wait(action_api_url: str, action_api_process: subprocess.Popen | None, config: DashboardConfig) -> None:
    """Open browser, register signal handlers, and block until exit."""
    log_success(f"Dashboard running at {action_api_url}")

    if config.open_browser:
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

    signal.signal(signal.SIGTSTP, _handle_tstp)

    try:
        if action_api_process:
            _wait_for_process(action_api_process)
        else:
            signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        _stop_children()


def run_dashboard(config: DashboardConfig) -> int:
    """Start the dashboard: resolve paths, launch the action API, and serve until exit."""
    config = _resolve_paths_and_build(config)
    validate_paths(config)

    log_info("Starting dashboard...")
    log_info(f"Reports: {config.reports_dir}")
    log_info(f"Static:  {config.static_dist}")
    log_info(f"Port:    {config.port}")

    action_api_host = config.api_host or DEFAULT_HOST
    action_api_port = config.api_port or config.port
    static_dist = config.static_dist
    if config.api_forced:
        action_api_url, action_api_process = _ensure_action_api_forced(
            action_api_host, action_api_port, static_dist=static_dist,
        )
    else:
        _kill_stale_action_api(action_api_host, action_api_port)
        action_api_url, action_api_process = _ensure_action_api(
            action_api_host, action_api_port, static_dist=static_dist,
        )

    _serve_and_wait(action_api_url, action_api_process, config)
    return 0
