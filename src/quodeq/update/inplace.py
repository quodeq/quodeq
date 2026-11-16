"""In-place upgrade for pip-style installs, started from the app.

Runs the same command ``quodeq upgrade`` runs (pipx, uv tool, Homebrew, or
this interpreter's pip), keeps its output for the UI, and on request restarts
Quodeq through ``quodeq restart`` so the new version loads. Offered only where
the install method is known for sure: never for the bundled app, an editable
checkout, or a pip environment we cannot or must not write to.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import sysconfig
import threading
from collections.abc import Callable
from pathlib import Path

import quodeq
from quodeq.shared.env_resolve import resolve_env
from quodeq.shared.fault_isolation import run_isolated
from quodeq.shared.utils import IS_WIN32
from quodeq.shared.win_launch import find_program, program_argv
from quodeq.update.channel import TOOL_BREW, detect_tool, upgrade_argv

_logger = logging.getLogger(__name__)

REASON_FROZEN = "frozen"  # the bundled app updates through its own download
REASON_EDITABLE = "editable"  # a source checkout; PyPI must not replace it
REASON_NO_TOOL = "no_tool"  # pipx/uv/brew is not on PATH
REASON_EXTERNALLY_MANAGED = "externally_managed"  # PEP 668 system Python
REASON_NOT_WRITABLE = "not_writable"  # pip cannot write to site-packages

PHASE_IDLE = "idle"
PHASE_UPGRADING = "upgrading"
PHASE_INSTALLED = "installed"
PHASE_ERROR = "error"

_INSTALL_DIRS = frozenset({"site-packages", "dist-packages"})
_EXTERNALLY_MANAGED_MARKER = "EXTERNALLY-MANAGED"
_UPGRADE_TIMEOUT_S = 900  # brew can compile; pip finishes in seconds
_OUTPUT_TAIL_CHARS = 4000  # enough for the error pip or brew ends with
_RESTART_ARGS = ("restart",)
# Points into the install being replaced (Homebrew removes the old keg), so the
# relaunched launcher must work it out again.
_STALE_ENV = ("QUODEQ_STATIC_DIST",)

_TEST_JOIN_TIMEOUT_S = 5

_lock = threading.Lock()
_state: dict = {"phase": PHASE_IDLE, "error": None, "output": "", "version": None}
_thread: threading.Thread | None = None


def _package_dir(package_file: str | None) -> Path:
    return Path(package_file or quodeq.__file__).resolve().parent


def _externally_managed() -> bool:
    """A PEP 668 system Python outside any virtual environment."""
    if sys.prefix != sys.base_prefix:
        return False
    return (Path(sysconfig.get_path("stdlib")) / _EXTERNALLY_MANAGED_MARKER).exists()


def unsupported_reason(
    env: dict[str, str] | None = None,
    package_file: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    """Why this install cannot upgrade itself from the app, None when it can."""
    argv = upgrade_argv(env, package_file)
    if argv is None:
        return REASON_FROZEN
    package_dir = _package_dir(package_file)
    if not _INSTALL_DIRS.intersection(package_dir.parts):
        return REASON_EDITABLE
    if find_program(argv[0], which=which) is None:
        return REASON_NO_TOOL
    if detect_tool(resolve_env(env), package_file) is None:  # the pip fallback
        if _externally_managed():
            return REASON_EXTERNALLY_MANAGED
        if not os.access(package_dir.parent, os.W_OK):
            return REASON_NOT_WRITABLE
    return None


def _set(**fields) -> None:
    with _lock:
        _state.update(fields)


def describe(env: dict[str, str] | None = None) -> dict:
    """Whether the app can upgrade this install, plus the running job's state."""
    reason = unsupported_reason(env)
    with _lock:
        snapshot = dict(_state)
    return {"supported": reason is None, "reason": reason, **snapshot}


def start(
    target_version: str | None,
    env: dict[str, str] | None = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    """Start the upgrade on a daemon thread. False while one runs or after one succeeded."""
    global _thread
    argv = upgrade_argv(env)
    if argv is None:
        return False
    with _lock:
        if _state["phase"] in (PHASE_UPGRADING, PHASE_INSTALLED):
            return False
        _state.update(phase=PHASE_UPGRADING, error=None, output="", version=target_version)
    _thread = threading.Thread(
        target=lambda: run_isolated(
            lambda: _run_upgrade(argv, run),
            label="in-place upgrade",
            log=_logger,
            on_error=lambda _exc: _set(phase=PHASE_ERROR, error="The upgrade stopped unexpectedly."),
        ),
        daemon=True,
    )
    _thread.start()
    return True


def _tail(stdout: str | bytes | None, stderr: str | bytes | None) -> str:
    """The last part of the tool's output; a timeout hands back bytes."""
    text = "".join(
        part.decode("utf-8", "replace") if isinstance(part, bytes) else part
        for part in (stdout, stderr) if part
    )
    return text[-_OUTPUT_TAIL_CHARS:]


def _run_upgrade(argv: list[str], run: Callable[..., subprocess.CompletedProcess]) -> None:
    try:
        result = run(
            program_argv(argv), capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=_UPGRADE_TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = _tail(exc.stdout, exc.stderr)
        _logger.warning("in-place upgrade timed out after %ss: %s", _UPGRADE_TIMEOUT_S, output)
        _set(phase=PHASE_ERROR, error="The upgrade took too long and was stopped.", output=output)
        return
    except OSError as exc:  # the tool vanished between the check and the run
        _logger.warning("in-place upgrade could not start: %s", exc)
        _set(phase=PHASE_ERROR, error=f"Could not start {argv[0]}.")
        return
    output = _tail(result.stdout, result.stderr)
    if result.returncode != 0:
        _logger.warning("in-place upgrade exited %s: %s", result.returncode, output)
        _set(phase=PHASE_ERROR, error=f"{argv[0]} exited with code {result.returncode}.", output=output)
        return
    _set(phase=PHASE_INSTALLED, output=output)


def _relaunch_argv(env: dict[str, str] | None, which: Callable[[str], str | None]) -> list[str]:
    """The launcher of the upgraded install.

    Homebrew deletes the old keg, and this interpreter with it, so it goes
    through the ``quodeq`` on PATH; every other tool keeps the environment.
    """
    if detect_tool(resolve_env(env)) == TOOL_BREW:
        launcher = which("quodeq")
        if launcher:
            return [launcher, *_RESTART_ARGS]
    return [sys.executable, "-m", "quodeq.cli", *_RESTART_ARGS]


def _detached_kwargs() -> dict:
    if IS_WIN32:
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def restart(
    env: dict[str, str] | None = None,
    popen: Callable[..., object] = subprocess.Popen,
    which: Callable[[str], str | None] = shutil.which,
) -> bool:
    """Spawn ``quodeq restart`` detached, so it outlives this API. Only after a successful upgrade."""
    with _lock:
        if _state["phase"] != PHASE_INSTALLED:
            return False
    child_env = {k: v for k, v in resolve_env(env).items() if k not in _STALE_ENV}
    popen(
        _relaunch_argv(env, which), env=child_env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **_detached_kwargs(),
    )
    return True


def _join_for_tests() -> None:
    thread = _thread
    if thread is not None:
        thread.join(timeout=_TEST_JOIN_TIMEOUT_S)


def _reset_for_tests() -> None:
    _join_for_tests()
    _set(phase=PHASE_IDLE, error=None, output="", version=None)
