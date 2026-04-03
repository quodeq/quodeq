"""Process management — PID tracking, stale-process cleanup, and process waiting."""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from quodeq.dashboard._api_health import ApiConfig, spawn_and_wait
from quodeq.dashboard._networking import _is_port_open
from quodeq.shared.config_loader import get_default_host as _get_default_host
from quodeq.shared.logging import log_debug
from quodeq.shared.utils import IS_WIN32

_POLL_INTERVAL_S = 0.1
_PROCESS_WAIT_TIMEOUT_S = 5
_STALE_KILL_DEADLINE_S = 3


def _terminate_pid(pid: int) -> None:
    """Send a termination signal to a process, platform-aware."""
    os.kill(pid, signal.SIGTERM if not IS_WIN32 else signal.CTRL_BREAK_EVENT)


def _get_pid_file(env: dict[str, str] | None = None) -> Path:
    """Return a PID file path in a user-private runtime directory.

    Override the default location via ``QUODEQ_RUN_DIR``.
    """
    env_run_dir = (env or os.environ).get("QUODEQ_RUN_DIR")
    run_dir = Path(env_run_dir) if env_run_dir else Path.home() / ".quodeq" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "action_api.pid"


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


def _spawn_and_wait_local(
    port: int, base_url: str, api_config: ApiConfig | None = None,
) -> tuple[str, subprocess.Popen]:
    """Spawn the action API on *port* and wait for it to become healthy."""
    return spawn_and_wait(port, base_url, _get_pid_file(), _get_default_host(), api_config)


def _wait_for_process(proc: subprocess.Popen) -> None:
    """Block until *proc* terminates, polling every 5 seconds."""
    while proc.poll() is None:
        try:
            proc.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            pass
