"""Quodeq menu bar app for macOS — manages the dashboard server."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import urllib.error
import urllib.request
import webbrowser

import rumps

_HEALTH_TIMEOUT = 1.0
_POLL_INTERVAL = 5
_MAX_START_RETRIES = 20
_PROCESS_PATTERNS = ("quodeq.api.app", "quodeq.action_api", "quodeq dashboard")
# macOS-specific paths for Homebrew and user-local binaries
_EXTRA_PATH_DIRS = "/usr/local/bin:/opt/homebrew/bin"


def _load_config(env=None):
    """Read port configuration from the environment (or an injected mapping)."""
    env = env or os.environ
    app_port = int(env.get("QUODEQ_PORT", "4180"))
    ports = tuple(int(p) for p in env.get("QUODEQ_PORTS", "4180,4181,4182,4183").split(","))
    return app_port, ports


def _health_check(port: int) -> bool:
    try:
        url = f"http://127.0.0.1:{port}/api/health"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return json.loads(r.read()).get("ok") is True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


def _source_user_path() -> None:
    """Load the user's shell PATH since .app bundles don't inherit it."""
    try:
        cmd = ('source ~/.zprofile 2>/dev/null; source ~/.zshrc 2>/dev/null; '
               'source ~/.bash_profile 2>/dev/null; echo $PATH')
        shell = os.environ.get("SHELL", "/bin/zsh")
        result = subprocess.run([shell, "-c", cmd], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            os.environ["PATH"] = result.stdout.strip()
            return
    except (subprocess.TimeoutExpired, OSError):
        pass
    extra = f"{os.path.expanduser('~/.local/bin')}:{_EXTRA_PATH_DIRS}"
    os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{extra}"


def _find_icon(name: str) -> str | None:
    """Find a menu bar icon by filename."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in [here, os.path.join(os.path.dirname(here), "Resources")]:
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return None


def _is_evaluating(port: int) -> bool:
    """Check if any evaluation job is currently running."""
    try:
        url = f"http://127.0.0.1:{port}/api/evaluations"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return any(j.get("status") == "running" for j in json.loads(r.read()))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


class QuodeqApp(rumps.App):
    def __init__(self):
        super().__init__("Quodeq", icon=_find_icon("menubar_iconTemplate.png"), template=True)
        self._app_port, self._ports = _load_config()
        self._commands_cache: dict[str, str | None] | None = None
        self._last_known_port: int | None = None
        self._process: subprocess.Popen | None = None
        self._port: int | None = None
        self._starting = False
        self._icon_stopped = _find_icon("menubar_iconTemplate.png")
        self._icon_running = _find_icon("menubar_icon_running.png")
        self._icon_evaluating = _find_icon("menubar_icon_evaluating.png")
        self._status_item = rumps.MenuItem("Stopped")
        self._open_item = rumps.MenuItem("Open Dashboard", callback=None)
        self._start_item = rumps.MenuItem("Start", callback=self._on_start)
        self._stop_item = rumps.MenuItem("Stop", callback=None)
        self._prereq_items: dict[str, rumps.MenuItem] = {}
        self.menu = [
            self._open_item, None, self._status_item, None,
            self._start_item, self._stop_item, None,
        ]
        threading.Thread(target=self._check_prereqs_and_start, daemon=True).start()

    def _find_commands(self) -> dict[str, str | None]:
        """Check which required commands are available (cached after first call)."""
        if self._commands_cache is not None:
            return self._commands_cache
        cmds = {}
        for name in ("python3", "node", "claude", "quodeq"):
            try:
                result = subprocess.run(
                    ["which", name], capture_output=True, text=True, timeout=5,
                )
                cmds[name] = result.stdout.strip() if result.returncode == 0 else None
            except (subprocess.TimeoutExpired, OSError):
                cmds[name] = None
        self._commands_cache = cmds
        return cmds

    def _find_running_port(self) -> int | None:
        """Find the running dashboard port, checking last known port first."""
        if self._last_known_port is not None and _health_check(self._last_known_port):
            return self._last_known_port
        for port in self._ports:
            if _health_check(port):
                self._last_known_port = port
                return port
        self._last_known_port = None
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
            self._status_item.title = "Stopped"
            self.icon = self._icon_stopped
            self.template = True
            self._set_ui_state(running=False)

    def _check_prereqs_and_start(self):
        """Check prerequisites, show status in menu, then auto-start."""
        import time
        time.sleep(1.0)
        cmds = self._find_commands()
        prereqs = [
            ("Python", "python3", cmds.get("python3")),
            ("Node.js", "node", cmds.get("node")),
            ("Claude", "claude", cmds.get("claude")),
            ("Quodeq", "quodeq", cmds.get("quodeq")),
        ]
        all_ok = True
        for label, cmd, path in prereqs:
            if not path:
                item = rumps.MenuItem(f"  {label} \u2717 not found", callback=None)
                self._prereq_items[cmd] = item
                self.menu.add(item)
                all_ok = False
        if not all_ok:
            self._start_item.set_callback(None)
            self._start_item._menuitem.setEnabled_(False)
            return
        if not cmds.get("quodeq"):
            self._prereq_items["quodeq"].title = "  Quodeq \u2014 installing..."
            try:
                subprocess.run(
                    ["python3", "-m", "pip", "install", "--user", "quodeq"],
                    capture_output=True, timeout=120,
                )
                site_bin = subprocess.run(
                    ["python3", "-m", "site", "--user-base"],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
                os.environ["PATH"] += f":{site_bin}/bin"
                self._prereq_items["quodeq"].title = "  Quodeq \u2713"
            except (subprocess.TimeoutExpired, OSError):
                self._prereq_items["quodeq"].title = "  Quodeq \u2717 install failed"
                return
        time.sleep(0.5)
        if self._find_running_port() is None:
            self._do_start()

    def _on_open(self, _):
        port = self._port or self._find_running_port()
        if port:
            webbrowser.open(f"http://127.0.0.1:{port}")

    def _on_start(self, _):
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        if self._starting or self._find_running_port():
            return
        self._starting = True
        try:
            self._do_start_inner()
        finally:
            self._starting = False

    def _do_start_inner(self):
        quodeq_cmd = self._find_commands().get("quodeq")
        if not quodeq_cmd:
            return
        self._status_item.title = "Starting..."
        try:
            self._process = subprocess.Popen(
                [quodeq_cmd, "dashboard", "--no-open", "--port", str(self._app_port)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            rumps.alert("Failed to start", str(e))
            return
        import time
        for _ in range(_MAX_START_RETRIES):
            time.sleep(0.5)
            port = self._find_running_port()
            if port:
                self._port = port
                return
        rumps.alert("Timeout", "Dashboard did not start in time.")

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


def main():
    _source_user_path()
    QuodeqApp().run()


if __name__ == "__main__":
    main()
