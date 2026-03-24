"""Quodeq menu bar app for macOS."""
from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import threading
import time
import webbrowser

import rumps

from _helpers import (
    find_commands as _find_commands,
    find_icon as _find_icon,
    health_check as _health_check,
    is_evaluating as _is_evaluating,
    source_user_path as _source_user_path,
)

_POLL_INTERVAL = 5
_MAX_START_RETRIES = 20
_PROCESS_PATTERNS = ("quodeq.api.app", "quodeq.action_api", "quodeq dashboard")
_AUTO_START_DELAY_S = 1.5
_HEALTH_POLL_INTERVAL_S = 0.5
_STDERR_READ_MAX = 500
_ERROR_DISPLAY_MAX = 200


def _load_config(env=None):
    """Read port configuration from the environment (or an injected mapping)."""
    env = env or os.environ
    app_port = int(env.get("QUODEQ_PORT", "4173"))
    ports = tuple(int(p) for p in env.get("QUODEQ_PORTS", "4173,4174,4175,4180,4181,4182,4183").split(","))
    return app_port, ports


class QuodeqApp(rumps.App):
    def __init__(self):
        super().__init__("Quodeq", icon=_find_icon("menubar_iconTemplate.png"), template=True)
        self._app_port, self._ports = _load_config()
        self._last_known_port: int | None = None
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
        cmds = _find_commands()
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
        """Find the running dashboard port, checking last known port first (TTL-cached)."""
        now = time.monotonic()
        if hasattr(self, '_port_cache_time') and (now - self._port_cache_time) < _POLL_INTERVAL:
            return self._port_cached_result
        if self._last_known_port is not None and _health_check(self._last_known_port):
            self._port_cached_result = self._last_known_port
            self._port_cache_time = now
            return self._last_known_port
        for port in self._ports:
            if _health_check(port):
                self._last_known_port = port
                self._port_cached_result = port
                self._port_cache_time = now
                return port
        self._last_known_port = None
        self._port_cached_result = None
        self._port_cache_time = now
        return None

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
        port = self._find_running_port()
        if port:
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
        port = self._port or self._find_running_port()
        if port:
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
        path = self._stderr_log_path
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
            self._stderr_log_path = None

    def _build_dashboard_cmd(self, quodeq_cmd: str) -> list[str]:
        """Build the dashboard command, probing --help for supported flags."""
        cmd = [quodeq_cmd, "dashboard"]
        try:
            help_out = subprocess.run(
                [quodeq_cmd, "dashboard", "--help"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            if "--no-open" in help_out:
                cmd.append("--no-open")
            if "--port" in help_out:
                cmd.extend(["--port", str(self._app_port)])
        except (subprocess.TimeoutExpired, OSError):
            pass
        return cmd

    def _do_start_inner(self):
        cmds = _find_commands()
        quodeq_cmd = cmds.get("quodeq")
        if not quodeq_cmd:
            self._set_error("quodeq not in PATH")
            self._status_item.title = "Stopped"
            return
        self._status_item.title = "Starting..."
        stderr_log = tempfile.NamedTemporaryFile(
            prefix="quodeq-dashboard-", suffix=".log", delete=False, mode="w",
        )
        self._stderr_log_path = stderr_log.name
        try:
            cmd = self._build_dashboard_cmd(quodeq_cmd)
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=stderr_log, start_new_session=True,
            )
        except OSError as e:
            self._set_error(f"Failed: {e}")
            self._status_item.title = "Stopped"
            return
        self._wait_for_dashboard(stderr_log)

    def _wait_for_dashboard(self, stderr_log):
        """Poll until the dashboard responds or process crashes."""
        for _ in range(_MAX_START_RETRIES):
            time.sleep(_HEALTH_POLL_INTERVAL_S)
            if self._process.poll() is not None:
                stderr_log.close()
                try:
                    with open(stderr_log.name) as f:
                        err = f.read(_STDERR_READ_MAX).strip()
                except OSError:
                    err = "unknown error"
                self._set_error(f"Crashed (exit {self._process.returncode}): {err[:_ERROR_DISPLAY_MAX]}")
                self._status_item.title = "Stopped"
                self._cleanup_stderr_log()
                return
            port = self._find_running_port()
            if port:
                self._port = port
                self._clear_error()
                return
        self._set_error("Timeout: dashboard did not respond")
        self._status_item.title = "Stopped"
        self._cleanup_stderr_log()

    @staticmethod
    def _kill_port_processes(port: int) -> None:
        """Send SIGTERM to all processes listening on *port*."""
        try:
            result = subprocess.run(
                ["lsof", f"-ti:{port}"], capture_output=True, text=True, timeout=5,
            )
            for pid in result.stdout.strip().split("\n"):
                if pid.strip():
                    try:
                        os.kill(int(pid.strip()), signal.SIGTERM)
                    except (OSError, ValueError):
                        pass
        except (subprocess.TimeoutExpired, OSError):
            pass

    def _on_stop(self, _):
        if self._process and self._process.poll() is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                self._process.terminate()
            self._process = None
        for port in self._ports:
            self._kill_port_processes(port)
        for pattern in _PROCESS_PATTERNS:
            try:
                subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass
        self._port = None
        self._status_item.title = "Stopped"
        self._set_ui_state(running=False)
        self._cleanup_stderr_log()


def main():
    _source_user_path()
    QuodeqApp().run()


if __name__ == "__main__":
    main()
