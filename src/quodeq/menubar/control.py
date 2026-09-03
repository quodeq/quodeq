"""Menu bar process control — pidfile singleton plus spawn/stop.

Used by the dashboard runner (spawn at launch when the preference is on),
the Flask API (Settings toggle), and the menu bar app itself (pidfile
ownership). The pidfile lives beside the dashboard's other runtime files in
<QUODEQ_RUN_DIR or ~/.quodeq/run>/menubar.pid.
"""
from __future__ import annotations

import importlib.util
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from quodeq.dashboard._frozen import is_frozen, subprocess_cmd

_logger = logging.getLogger(__name__)
_PIDFILE_NAME = "menubar.pid"


def _pidfile_path() -> Path:
    run_dir = Path(os.environ.get("QUODEQ_RUN_DIR", Path.home() / ".quodeq" / "run"))
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / _PIDFILE_NAME


def is_supported() -> bool:
    """True when this install can show a menu bar icon (macOS + rumps)."""
    if sys.platform != "darwin":
        return False
    if is_frozen():
        return True
    try:
        return importlib.util.find_spec("rumps") is not None
    except (ImportError, ValueError):
        return False


def _read_pid() -> int | None:
    try:
        return int(_pidfile_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def is_running() -> bool:
    """True when a live menu bar process owns the pidfile. Cleans stale files."""
    pid = _read_pid()
    if pid is None:
        remove_pidfile()
        return False
    if not _pid_alive(pid):
        remove_pidfile()
        return False
    return True


def write_pidfile() -> None:
    """Record this process as the menu bar owner."""
    try:
        _pidfile_path().write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        _logger.debug("could not write menubar pidfile", exc_info=True)


def remove_pidfile() -> None:
    try:
        _pidfile_path().unlink()
    except OSError:
        pass


def spawn() -> bool:
    """Launch the menu bar as a detached subprocess. False when skipped."""
    if not is_supported() or is_running():
        return False
    try:
        subprocess.Popen(
            subprocess_cmd("menubar"),
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError:
        _logger.warning("could not launch the menu bar process", exc_info=True)
        return False


def stop() -> bool:
    """Terminate the menu bar process named by the pidfile. False when none."""
    if not is_running():
        return False
    pid = _read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        _logger.debug("could not SIGTERM menubar pid %s", pid, exc_info=True)
    remove_pidfile()
    return True
