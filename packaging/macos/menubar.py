"""Quodeq menu bar app for macOS."""
from __future__ import annotations

import logging as _logging
import os
import signal
import subprocess
import threading
import time
import webbrowser

import rumps

_PKILL_TIMEOUT_S = 5

from _helpers import (
    find_commands as _find_commands,
    find_icon as _find_icon,
    is_evaluating as _is_evaluating,
    source_user_path as _source_user_path,
)
from _dashboard import (
    build_dashboard_cmd as _build_dashboard_cmd,
    cleanup_stderr_log as _cleanup_stderr_log_file,
    DashboardCallbacks as _DashboardCallbacks,
    DashboardState as _DashboardState,
    find_pids_on_port as _find_pids_on_port,
    find_running_port as _find_running_port_cached,
    kill_port_processes as _kill_port_processes,
    open_stderr_log as _open_stderr_log,
    wait_for_dashboard as _wait_for_dashboard,
    _STDERR_READ_MAX,
    _ERROR_DISPLAY_MAX,
)

_DEFAULT_APP_PORT = 7863
try:
    _POLL_INTERVAL = int(os.environ.get("QUODEQ_POLL_INTERVAL", "5"))
except ValueError:
    _logging.getLogger(__name__).warning("Invalid QUODEQ_POLL_INTERVAL; using default 5")
    _POLL_INTERVAL = 5
_PROCESS_PATTERNS = ("quodeq.api.app", "quodeq.action_api", "quodeq dashboard")
try:
    _AUTO_START_DELAY_S = float(os.environ.get("QUODEQ_AUTO_START_DELAY_S", "1.5"))
except ValueError:
    _logging.getLogger(__name__).warning("Invalid QUODEQ_AUTO_START_DELAY_S; using default 1.5")
    _AUTO_START_DELAY_S = 1.5
_DEFAULT_PORTS = "7863,7864,7865,7866,7867,7868,7869"


def _load_config(env=None):
    """Read port configuration from the environment (or an injected mapping)."""
    _cfg_log = _logging.getLogger(__name__)
    env = env or os.environ
    try:
        app_port = int(env.get("QUODEQ_PORT", str(_DEFAULT_APP_PORT)))
    except ValueError:
        _cfg_log.warning("Invalid QUODEQ_PORT; using default %d", _DEFAULT_APP_PORT)
        app_port = _DEFAULT_APP_PORT
    raw_ports = env.get("QUODEQ_PORTS", _DEFAULT_PORTS)
    ports_list = []
    for p in raw_ports.split(","):
        try:
            ports_list.append(int(p))
        except ValueError:
            _cfg_log.warning("Invalid port value %r in QUODEQ_PORTS; skipping", p)
    ports = tuple(ports_list) if ports_list else tuple(int(p) for p in _DEFAULT_PORTS.split(","))
    return app_port, ports


class QuodeqApp(rumps.App):
    def __init__(self):
        super().__init__("Quodeq", icon=_find_icon("menubar_iconTemplate.png"), template=True)
        self._app_port, self._ports = _load_config()
        self._port_cache: dict = {}  # shared cache dict for find_running_port helper
        self._process: subprocess.Popen | None = None
        self._port: int | None = None
        self._starting = False
        self._state_lock = threading.Lock()
        self._stderr_log_path: str | None = None
        self._icon_stopped = _find_icon("menubar_iconTemplate.png")
        self._icon_running = _find_icon("menubar_icon_running.png")
        self._icon_evaluating = _find_icon("menubar_icon_evaluating.png")
        self._status_item = rumps.MenuItem("Stopped")
        self._open_item = rumps.MenuItem("Open Dashboard", callback=None)
        self._start_item = rumps.MenuItem("Start", callback=self._on_start)
        self._stop_item = rumps.MenuItem("Stop", callback=None)
        self._error_item = rumps.MenuItem("")

        # Check prereqs on main thread so menu items render correctly
        self._cached_cmds = _find_commands()
        cmds = self._cached_cmds
        self._prereq_items = {}
        for label, cmd in [("Python", "python3"), ("Node.js", "node"), ("Claude", "claude"), ("Quodeq", "quodeq")]:
            path = cmds.get(cmd)
            if path:
                item = rumps.MenuItem(f"  {label} \u2713", callback=None)
            else:
                item = rumps.MenuItem(f"  {label} \u2717 not found", callback=None)
            self._prereq_items[cmd] = item

        self.menu = [
            self._open_item, None, self._status_item, self._error_item, None,
            self._start_item, self._stop_item, None,
            *self._prereq_items.values(),
        ]
        # Auto-start in background
        threading.Thread(target=self._auto_start, daemon=True).start()

    def _set_error(self, msg: str) -> None:
        """Show an error in the menu (thread-safe — menu title updates work from any thread)."""
        self._error_item.title = msg

    def _clear_error(self) -> None:
        self._error_item.title = ""

    def _find_running_port(self) -> int | None:
        """Find the running dashboard port (delegates to cached helper)."""
        result = _find_running_port_cached(self._ports, self._port_cache.get("last_known"), self._port_cache)
        return result

    def _set_ui_state(self, running: bool) -> None:
        """Toggle menu items between running and stopped states."""
        if running:
            self._open_item.set_callback(self._on_open)
            self._open_item._menuitem.setEnabled_(True)
            self._start_item.set_callback(None)
            self._start_item._menuitem.setEnabled_(False)
            self._stop_item.set_callback(self._on_stop)
            self._stop_item._menuitem.setEnabled_(True)
        else:
            self._open_item.set_callback(None)
            self._open_item._menuitem.setEnabled_(False)
            self._start_item.set_callback(self._on_start)
            self._start_item._menuitem.setEnabled_(True)
            self._stop_item.set_callback(None)
            self._stop_item._menuitem.setEnabled_(False)

    @rumps.timer(_POLL_INTERVAL)
    def _poll(self, _):
        """Periodically check if the dashboard is running."""
        with self._state_lock:
            port = self._port
        if port and not _health_check(port):
            port = None
        if not port:
            port = self._find_running_port()
        if port:
            with self._state_lock:
                self._port = port
            self._clear_error()
            if _is_evaluating(port):
                self._status_item.title = "Evaluating..."
                self.icon = self._icon_evaluating
            else:
                self._status_item.title = f"Running on port {port}"
                self.icon = self._icon_running
            self.template = False
            self._set_ui_state(running=True)
        else:
            with self._state_lock:
                self._port = None
            if not self._starting:
                self._status_item.title = "Stopped"
            self.icon = self._icon_stopped
            self.template = True
            self._set_ui_state(running=False)

    def _auto_start(self):
        """Auto-start the dashboard if not already running."""
        time.sleep(_AUTO_START_DELAY_S)
        if self._find_running_port() is None:
            self._do_start()

    def _on_open(self, _):
        with self._state_lock:
            port = self._port
        port = port or self._find_running_port()
        if not port:
            return
        quodeq_cmd = self._cached_cmds.get("quodeq")
        if quodeq_cmd:
            # Launches PyWebView window (or brings existing one to front via socket IPC)
            subprocess.Popen(
                [quodeq_cmd, "dashboard", "--no-build", "--port", str(port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            webbrowser.open(f"http://127.0.0.1:{port}")

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

    def _launch_dashboard_process(self, quodeq_cmd: str, stderr_log) -> bool:
        """Launch the dashboard subprocess. Returns True on success, False on failure."""
        try:
            cmd = _build_dashboard_cmd(quodeq_cmd, self._app_port)
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
        cmds = self._cached_cmds
        quodeq_cmd = cmds.get("quodeq")
        if not quodeq_cmd:
            self._set_error("quodeq not in PATH. Install with 'pip install quodeq' or add its location to your PATH.")
            self._status_item.title = "Stopped"
            return
        self._status_item.title = "Starting..."
        stderr_log = _open_stderr_log()
        self._stderr_log_path = stderr_log.name
        if not self._launch_dashboard_process(quodeq_cmd, stderr_log):
            return
        self._wait_for_dashboard(stderr_log)

    def _handle_crashed_process(self, stderr_log) -> None:
        """Report a crashed dashboard process and clean up."""
        stderr_log.close()
        try:
            with open(stderr_log.name) as f:
                err = f.read(_STDERR_READ_MAX).strip()
        except OSError:
            err = "unknown error"
        sanitized = err[:_ERROR_DISPLAY_MAX].replace("\n", " ").strip()
        self._set_error(
            f"Dashboard stopped unexpectedly (exit code {self._process.returncode}). "
            f"Try restarting. Details: {sanitized}" if sanitized else
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


def main():
    _source_user_path()
    QuodeqApp().run()


if __name__ == "__main__":
    main()
