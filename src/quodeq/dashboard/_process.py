"""Process management — PID tracking, stale-process cleanup, and process waiting."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

from quodeq.dashboard._api_health import ApiConfig, action_api_healthy, spawn_and_wait
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
    if env_run_dir and not Path(env_run_dir).is_absolute():
        raise ValueError(f"QUODEQ_RUN_DIR must be an absolute path, got: {env_run_dir!r}")
    run_dir = Path(env_run_dir) if env_run_dir else Path.home() / ".quodeq" / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "action_api.pid"


def _read_pid_record(pid_file: Path) -> dict | None:
    """Return the recorded API endpoint as ``{pid, host, port}``, or None.

    Tolerates the legacy bare-integer file written by older versions (and by a
    differently-versioned quodeq sharing this run dir), reporting host/port as
    None so the caller falls back to the endpoint it was about to use.
    """
    try:
        raw = pid_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        log_debug(f"Could not read PID file: {exc}")
        return None
    if not raw:
        return None
    try:
        record = json.loads(raw)
    except ValueError:
        log_debug(f"Unrecognized PID file contents: {raw!r}")
        return None
    # A bare integer is the legacy format — and note json.loads parses it
    # happily, so it never reaches an int() fallback.
    if _is_pid(record):
        return {"pid": record, "host": None, "port": None}
    if not isinstance(record, dict) or not _is_pid(record.get("pid")):
        log_debug(f"Unrecognized PID file contents: {raw!r}")
        return None
    return record


def _is_pid(value: object) -> bool:
    """True for a plausible pid. Excludes bool, which is an int in Python."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _kill_stale_action_api(host: str, port: int) -> None:
    """Kill a *stale* action API recorded in the PID file.

    An API that still answers /api/health is left alone. It used to be killed
    unconditionally, which meant every launch executed the previous launch's
    backend: the running window kept its dead Flask server, could never load
    projects, and sat on the loading screen forever. The recorded endpoint is
    health-checked rather than the requested one because ``_choose_ui_port``
    has already skipped the port the live API holds, so the two differ in
    exactly the case that matters.
    """
    pid_file = _get_pid_file()
    if pid_file.exists():
        record = _read_pid_record(pid_file)
        if record is not None and _recorded_api_healthy(record, host, port):
            log_debug("Action API in PID file is healthy; leaving it running")
            return
        if record is not None:
            try:
                _terminate_pid(record["pid"])
            except (ValueError, OSError) as exc:
                log_debug(f"Could not kill stale action API (pid file): {exc}")
        try:
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            log_debug(f"Could not remove stale PID file: {exc}")
    deadline = time.monotonic() + _STALE_KILL_DEADLINE_S
    while _is_port_open(host, port) and time.monotonic() < deadline:
        time.sleep(_POLL_INTERVAL_S)


def _recorded_api_healthy(record: dict, fallback_host: str, fallback_port: int) -> bool:
    """Return True if the API named by *record* is serving a healthy endpoint."""
    api_host = record.get("host") or fallback_host
    api_port = record.get("port") or fallback_port
    return action_api_healthy(f"http://{api_host}:{api_port}")


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
