"""Dashboard process management for the built-in menu bar app.

Ported from packaging/macos/_dashboard.py when the menu bar became a built-in
feature; the dashboard command itself now comes from
quodeq.shared.frozen.dashboard_cmd instead of probing a `quodeq` CLI.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from typing import NamedTuple

from quodeq.menubar._health import health_check as _health_check

_POLL_INTERVAL = 5
_MAX_START_RETRIES = 20
_HEALTH_POLL_INTERVAL_S = 0.5
_STDERR_READ_MAX = 500
_ERROR_DISPLAY_MAX = 200


class DashboardCallbacks(NamedTuple):
    """Callbacks for dashboard startup lifecycle events."""
    on_port_found: object  # (port: int, stderr_log) -> None
    on_crash: object       # (stderr_log) -> None
    on_timeout: object     # () -> None


class DashboardState(NamedTuple):
    """Mutable port-discovery state passed through the wait loop."""
    cache: dict
    last_known: int | None


def find_running_port(ports: tuple[int, ...], last_known: int | None, cache: dict) -> int | None:
    """Find the running dashboard port, checking last known port first (TTL-cached)."""
    now = time.monotonic()
    if (now - cache.get("time", 0)) < _POLL_INTERVAL:
        return cache.get("result")
    if last_known is not None and _health_check(last_known):
        cache["result"] = last_known
        cache["time"] = now
        return last_known
    for port in ports:
        if _health_check(port):
            cache["last_known"] = port
            cache["result"] = port
            cache["time"] = now
            return port
    cache["last_known"] = None
    cache["result"] = None
    cache["time"] = now
    return None


def cleanup_stderr_log(path: str | None) -> None:
    """Remove the stderr log tempfile if it exists."""
    if path:
        try:
            os.unlink(path)
        except OSError:
            pass


def find_pids_on_port(port: int) -> list[int]:
    """Return PIDs listening on *port*.

    macOS-only: relies on ``lsof`` which is available on macOS by default.
    """
    if sys.platform != "darwin":
        return []
    try:
        # int() enforces the argv boundary: whatever the caller passed, only a
        # plain integer ever reaches the lsof argument.
        result = subprocess.run(
            ["lsof", f"-ti:{int(port)}"], capture_output=True, text=True, encoding="utf-8",
            timeout=5,
        )
        return [int(pid.strip()) for pid in result.stdout.strip().split("\n") if pid.strip()]
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return []


def _is_quodeq_process(pid: int) -> bool:
    """Return True if *pid*'s command line looks like quodeq's own dashboard process."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, encoding="utf-8", timeout=2,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return "quodeq" in result.stdout.lower()


def kill_port_processes(port: int) -> None:
    """Send SIGTERM to quodeq's own processes listening on *port*."""
    for pid in find_pids_on_port(port):
        if not _is_quodeq_process(pid):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass


def wait_for_dashboard(
    process: subprocess.Popen,
    ports: tuple[int, ...],
    state: DashboardState,
    stderr_log,
    callbacks: DashboardCallbacks,
) -> None:
    """Poll until the dashboard responds or process crashes."""
    try:
        for _ in range(_MAX_START_RETRIES):
            time.sleep(_HEALTH_POLL_INTERVAL_S)
            if process.poll() is not None:
                callbacks.on_crash(stderr_log)
                return
            port = find_running_port(ports, state.last_known, state.cache)
            if port:
                callbacks.on_port_found(port, stderr_log)
                return
        callbacks.on_timeout()
    finally:
        try:
            stderr_log.close()
        except OSError:
            pass


def open_stderr_log(prefix: str = "quodeq-dashboard-") -> tempfile.NamedTemporaryFile:
    """Create a named temporary file for capturing stderr output."""
    return tempfile.NamedTemporaryFile(
        prefix=prefix, suffix=".log", delete=False, mode="w",
    )
