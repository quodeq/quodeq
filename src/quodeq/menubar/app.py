"""Quodeq menu bar app — built-in successor to the standalone QuodeqBar.

Runs in its own process (``--_menubar`` frozen, ``python -m quodeq.menubar``
in dev) so its rumps/AppKit run loop never competes with the pywebview
window's. Differences from the retired QuodeqBar app:

- No dashboard auto-start; the dashboard is what usually spawns this process.
- Launches the dashboard by re-executing its own binary (dashboard_cmd)
  instead of discovering a ``quodeq`` CLI on PATH.
- Quit flips the Settings preference off so the icon stays gone.
"""
from __future__ import annotations

import logging as _logging
import os
import signal
import subprocess
import threading

import rumps

from quodeq.dashboard._frozen import dashboard_cmd as _dashboard_cmd
from quodeq.dashboard._frozen import source_user_path as _source_user_path
from quodeq.menubar import control as _control
from quodeq.menubar import state as _state
from quodeq.menubar._health import (
    find_commands as _find_commands,
    find_icon as _find_icon,
    health_check as _health_check,
    is_evaluating as _is_evaluating,
)
from quodeq.menubar._process import (
    DashboardCallbacks as _DashboardCallbacks,
    DashboardState as _DashboardState,
    cleanup_stderr_log as _cleanup_stderr_log_file,
    find_running_port as _find_running_port_cached,
    kill_port_processes as _kill_port_processes,
    open_stderr_log as _open_stderr_log,
    wait_for_dashboard as _wait_for_dashboard,
    _ERROR_DISPLAY_MAX,
    _STDERR_READ_MAX,
)

_PKILL_TIMEOUT_S = 5
_DEFAULT_APP_PORT = 7863
try:
    _POLL_INTERVAL = int(os.environ.get("QUODEQ_POLL_INTERVAL", "5"))
except ValueError:
    _logging.getLogger(__name__).warning("Invalid QUODEQ_POLL_INTERVAL; using default 5")
    _POLL_INTERVAL = 5
_PROCESS_PATTERNS = ("quodeq.api.app", "quodeq.action_api", "quodeq dashboard")
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
        super().__init__(
            "Quodeq", icon=_find_icon("menubar_iconTemplate.png"), template=True,
            quit_button=None,
        )
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
        self._update_item = rumps.MenuItem("Check for Updates…", callback=self._on_check_updates)
        self._quit_item = rumps.MenuItem("Quit Quodeq Bar", callback=self._on_quit)

        # Check prereqs on main thread so menu items render correctly
        self._cached_cmds = _find_commands()
        cmds = self._cached_cmds
        self._prereq_items = {}
        for label, cmd in [("Python", "python3"), ("Node.js", "node"), ("Claude", "claude")]:
            path = cmds.get(cmd)
            if path:
                item = rumps.MenuItem(f"  {label} ✓", callback=None)
            else:
                item = rumps.MenuItem(f"  {label} ✗ not found", callback=None)
            self._prereq_items[cmd] = item

        self.menu = [
            self._open_item, None, self._status_item, self._error_item, None,
            self._start_item, self._stop_item, self._update_item, None,
            *self._prereq_items.values(), None,
            self._quit_item,
        ]

    def _set_error(self, msg: str) -> None:
        """Show an error in the menu (thread-safe — menu title updates work from any thread)."""
        self._error_item.title = msg

    def _clear_error(self) -> None:
        self._error_item.title = ""

    def _on_quit(self, _sender):
        """Quit the bar and flip the preference off so it stays gone.

        The Settings toggle is the other control surface; quitting here must
        not leave a preference that resurrects the icon on the next launch.
        """
        try:
            _state.set_enabled(False)
        except Exception:
            pass
        _control.remove_pidfile()
        rumps.quit_application()

    def _on_check_updates(self, _sender):
        """Force a check and report the result via a notification."""
        try:
            from quodeq.update.checker import get_status, run_check

            run_check(force=True)
            status = get_status()
            if status.get("update_available"):
                rumps.notification(
                    "Quodeq", "Update available",
                    f"{status['current']} → {status['latest']}",
                )
            else:
                rumps.notification("Quodeq", "Up to date", f"You're on {status['current']}.")
        except Exception:
            pass

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

        try:
            from quodeq.update.checker import get_status

            if get_status().get("update_available"):
                self._update_item.title = "Update Available. Click to view"
            else:
                self._update_item.title = "Check for Updates…"
        except Exception:
            pass

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


def _set_accessory_policy() -> None:
    """Keep this process out of the Dock; only the status item should show.

    A subprocess of the bundled app would otherwise activate as a regular
    app and add a second Dock icon beside the main window's.
    """
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory,
        )
    except Exception:
        _logging.getLogger(__name__).debug("could not set accessory policy", exc_info=True)


def main() -> None:
    _source_user_path()
    if _control.is_running():
        # Another bar owns the status item; a second icon would only confuse.
        return
    _set_accessory_policy()
    _control.write_pidfile()
    try:
        QuodeqApp().run()
    finally:
        _control.remove_pidfile()


if __name__ == "__main__":
    main()
