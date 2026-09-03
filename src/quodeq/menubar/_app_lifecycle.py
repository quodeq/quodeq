"""Dashboard start/stop/open lifecycle for the menu bar app.

Mixin methods for QuodeqApp (quodeq/menubar/app.py), split out for file size.
The host class provides the menu items (_status_item, _error_item, ...), the
_state_lock/_starting/_port/_process fields, _set_error/_clear_error,
_find_running_port, and _set_ui_state. Nothing here touches rumps directly,
so this module stays importable without the rumps stub tests use for app.py.
"""
from __future__ import annotations

import logging as _logging
import os
import signal
import subprocess
import threading

from quodeq.shared.frozen import dashboard_cmd as _dashboard_cmd
from quodeq.menubar._process import (
    DashboardCallbacks as _DashboardCallbacks,
    DashboardState as _DashboardState,
    cleanup_stderr_log as _cleanup_stderr_log_file,
    kill_port_processes as _kill_port_processes,
    open_stderr_log as _open_stderr_log,
    wait_for_dashboard as _wait_for_dashboard,
    _ERROR_DISPLAY_MAX,
    _STDERR_READ_MAX,
)

_PKILL_TIMEOUT_S = 5
_PROCESS_PATTERNS = ("quodeq.api.app", "quodeq.action_api", "quodeq dashboard")


class DashboardLifecycleMixin:
    """Start, stop, open, and crash-report the dashboard from the bar menu."""

    def _on_open(self, _):
        with self._state_lock:
            port = self._port
        port = port or self._find_running_port()
        if not port:
            return
        # Launches the dashboard app (or brings the existing window to the
        # front via its socket IPC) by re-executing our own binary.
        subprocess.Popen(
            _dashboard_cmd(["--no-build", "--port", str(port)]),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _on_start(self, _):
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        with self._state_lock:
            if self._starting:
                return
            if self._find_running_port():
                return
            self._starting = True
        self._clear_error()
        try:
            self._do_start_inner()
        except (OSError, subprocess.SubprocessError, ValueError) as e:
            self._set_error(f"Error: {e}")
            self._status_item.title = "Stopped"
            self._cleanup_stderr_log()
        finally:
            with self._state_lock:
                self._starting = False

    def _cleanup_stderr_log(self) -> None:
        """Remove the stderr log tempfile if it exists."""
        _cleanup_stderr_log_file(self._stderr_log_path)
        self._stderr_log_path = None

    def _launch_dashboard_process(self, stderr_log) -> bool:
        """Launch the dashboard subprocess. Returns True on success, False on failure."""
        try:
            cmd = _dashboard_cmd(["--no-open", "--port", str(self._app_port)])
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=stderr_log, start_new_session=True,
            )
            return True
        except OSError as e:
            stderr_log.close()
            self._set_error(f"Failed: {e}")
            self._status_item.title = "Stopped"
            self._cleanup_stderr_log()
            return False

    def _do_start_inner(self):
        self._status_item.title = "Starting..."
        stderr_log = _open_stderr_log()
        self._stderr_log_path = stderr_log.name
        if not self._launch_dashboard_process(stderr_log):
            return
        self._wait_for_dashboard(stderr_log)

    def _handle_crashed_process(self, stderr_log) -> None:
        """Report a crashed dashboard process and clean up."""
        stderr_log.close()
        try:
            with open(stderr_log.name, encoding="utf-8") as f:
                err = f.read(_STDERR_READ_MAX).strip()
        except OSError:
            err = "unknown error"
        sanitized = err[:_ERROR_DISPLAY_MAX].replace("\n", " ").strip()
        if sanitized:
            # Keep the crash detail in the local log for troubleshooting, but
            # do not surface raw dashboard stderr (which may include tokens or
            # filesystem paths) in the always-visible menu.
            _logging.getLogger(__name__).warning(
                "Dashboard crashed (exit code %s): %s", self._process.returncode, sanitized,
            )
        self._set_error(
            f"Dashboard stopped unexpectedly (exit code {self._process.returncode}). Try restarting."
        )
        self._status_item.title = "Stopped"
        self._cleanup_stderr_log()

    def _wait_for_dashboard(self, stderr_log):
        """Poll until the dashboard responds or process crashes."""
        def on_port_found(port, _log):
            with self._state_lock:
                self._port = port
            self._clear_error()
            self._cleanup_stderr_log()

        def on_timeout():
            self._set_error("Timeout: dashboard did not respond")
            self._status_item.title = "Stopped"
            self._cleanup_stderr_log()

        _wait_for_dashboard(
            process=self._process,
            ports=self._ports,
            state=_DashboardState(cache=self._port_cache, last_known=self._port_cache.get("last_known")),
            stderr_log=stderr_log,
            callbacks=_DashboardCallbacks(
                on_port_found=on_port_found,
                on_crash=self._handle_crashed_process,
                on_timeout=on_timeout,
            ),
        )

    def _on_stop(self, _):
        if self._process and self._process.poll() is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                self._process.terminate()
            self._process = None
        for port in self._ports:
            _kill_port_processes(port)
        for pattern in _PROCESS_PATTERNS:
            try:
                subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=_PKILL_TIMEOUT_S)
            except (subprocess.TimeoutExpired, OSError):
                pass
        with self._state_lock:
            self._port = None
        self._status_item.title = "Stopped"
        self._set_ui_state(running=False)
        self._cleanup_stderr_log()
