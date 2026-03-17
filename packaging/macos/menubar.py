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

_APP_PORT = 4180  # dedicated port for menu bar app
_PORTS = (4180, 4181, 4182, 4183)
_HEALTH_TIMEOUT = 1.0
_POLL_INTERVAL = 5


_commands_cache: dict[str, str | None] | None = None


def _find_commands() -> dict[str, str | None]:
    """Check which required commands are available (cached after first call)."""
    global _commands_cache
    if _commands_cache is not None:
        return _commands_cache
    cmds = {}
    for name in ("python3", "node", "claude", "quodeq"):
        try:
            result = subprocess.run(
                ["which", name], capture_output=True, text=True, timeout=5,
            )
            cmds[name] = result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, OSError):
            cmds[name] = None
    _commands_cache = cmds
    return cmds


def _health_check(port: int) -> bool:
    try:
        url = f"http://127.0.0.1:{port}/api/health"
        with urllib.request.urlopen(url, timeout=_HEALTH_TIMEOUT) as r:
            return json.loads(r.read()).get("ok") is True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


def _find_running_port() -> int | None:
    for port in _PORTS:
        if _health_check(port):
            return port
    return None


def _source_user_path() -> None:
    """Load the user's shell PATH since .app bundles don't inherit it."""
    # Source all profiles in one shell to get the complete PATH
    try:
        cmd = (
            'source ~/.zprofile 2>/dev/null; '
            'source ~/.zshrc 2>/dev/null; '
            'source ~/.bash_profile 2>/dev/null; '
            'echo $PATH'
        )
        result = subprocess.run(
            ["zsh", "-c", cmd],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            os.environ["PATH"] = result.stdout.strip()
            return
    except (subprocess.TimeoutExpired, OSError):
        pass
    # Fallback: add common locations manually
    extra = f"{os.path.expanduser('~/.local/bin')}:/usr/local/bin:/opt/homebrew/bin"
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
            jobs = json.loads(r.read())
            return any(j.get("status") == "running" for j in jobs)
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False


class QuodeqApp(rumps.App):
    def __init__(self):
        super().__init__(
            "Quodeq",
            icon=_find_icon("menubar_iconTemplate.png"),
            template=True,
        )
        self._process: subprocess.Popen | None = None
        self._port: int | None = None
        self._starting = False  # prevent double-start
        self._icon_stopped = _find_icon("menubar_iconTemplate.png")
        self._icon_running = _find_icon("menubar_icon_running.png")
        self._icon_evaluating = _find_icon("menubar_icon_evaluating.png")
        self._status_item = rumps.MenuItem("Stopped")
        self._open_item = rumps.MenuItem("Open Dashboard", callback=None)
        self._start_item = rumps.MenuItem("Start", callback=self._on_start)
        self._stop_item = rumps.MenuItem("Stop", callback=None)
        self._prereq_items: dict[str, rumps.MenuItem] = {}

        self.menu = [
            self._open_item,
            None,
            self._status_item,
            None,
            self._start_item,
            self._stop_item,
            None,
        ]

        # Check prerequisites and show status
        threading.Thread(target=self._check_prereqs_and_start, daemon=True).start()

    @rumps.timer(_POLL_INTERVAL)
    def _poll(self, _):
        """Periodically check if the dashboard is running."""
        port = _find_running_port()
        if port:
            self._port = port
            evaluating = _is_evaluating(port)
            if evaluating:
                self._status_item.title = "Evaluating..."
                self.icon = self._icon_evaluating
                self.template = False  # colored icon, not template
            else:
                self._status_item.title = f"Running on port {port}"
                self.icon = self._icon_running
                self.template = False
            self._open_item.set_callback(self._on_open)
            self._open_item._menuitem.setEnabled_(True)
            self._start_item.set_callback(None)
            self._start_item._menuitem.setEnabled_(False)
            self._stop_item.set_callback(self._on_stop)
            self._stop_item._menuitem.setEnabled_(True)
        else:
            self._port = None
            self._status_item.title = "Stopped"
            self.icon = self._icon_stopped
            self.template = True  # back to template for auto light/dark
            self._open_item.set_callback(None)
            self._open_item._menuitem.setEnabled_(False)
            self._start_item.set_callback(self._on_start)
            self._start_item._menuitem.setEnabled_(True)
            self._stop_item.set_callback(None)
            self._stop_item._menuitem.setEnabled_(False)

    def _check_prereqs_and_start(self):
        """Check prerequisites, show status in menu, then auto-start."""
        import time
        time.sleep(1.0)
        cmds = _find_commands()
        prereqs = [
            ("Python", "python3", cmds.get("python3")),
            ("Node.js", "node", cmds.get("node")),
            ("Claude", "claude", cmds.get("claude")),
            ("Quodeq", "quodeq", cmds.get("quodeq")),
        ]
        all_ok = True
        for label, cmd, path in prereqs:
            if not path:
                item = rumps.MenuItem(f"  {label} ✗ not found", callback=None)
                self._prereq_items[cmd] = item
                self.menu.add(item)
                all_ok = False

        if not all_ok:
            self._start_item.set_callback(None)
            self._start_item._menuitem.setEnabled_(False)
            return

        # Auto-install quodeq if missing but prerequisites are met
        if not cmds.get("quodeq"):
            self._prereq_items["quodeq"].title = "  Quodeq — installing..."
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
                self._prereq_items["quodeq"].title = "  Quodeq ✓"
            except (subprocess.TimeoutExpired, OSError):
                self._prereq_items["quodeq"].title = "  Quodeq ✗ install failed"
                return

        # Auto-start
        time.sleep(0.5)
        if _find_running_port() is None:
            self._do_start()

    def _on_open(self, _):
        port = self._port or _find_running_port()
        if port:
            webbrowser.open(f"http://127.0.0.1:{port}")

    def _on_start(self, _):
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self):
        if self._starting or _find_running_port():
            return
        self._starting = True
        try:
            self._do_start_inner()
        finally:
            self._starting = False

    def _do_start_inner(self):
        quodeq_cmd = _find_commands().get("quodeq")
        if not quodeq_cmd:
            return

        self._status_item.title = "Starting..."
        try:
            self._process = subprocess.Popen(
                [quodeq_cmd, "dashboard", "--no-open", "--port", str(_APP_PORT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            rumps.alert("Failed to start", str(e))
            return

        import time
        for _ in range(20):
            time.sleep(0.5)
            port = _find_running_port()
            if port:
                self._port = port
                return

        rumps.alert("Timeout", "Dashboard did not start in time.")

    def _on_stop(self, _):
        # Kill the dashboard process group
        if self._process and self._process.poll() is None:
            try:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                self._process.terminate()
            self._process = None

        # Kill any quodeq processes listening on our ports
        for port in _PORTS:
            try:
                result = subprocess.run(
                    ["lsof", f"-ti:{port}"],
                    capture_output=True, text=True, timeout=5,
                )
                for pid in result.stdout.strip().split("\n"):
                    if pid.strip():
                        try:
                            os.kill(int(pid.strip()), signal.SIGTERM)
                        except (OSError, ValueError):
                            pass
            except (subprocess.TimeoutExpired, OSError):
                pass

        # Also pkill as a fallback
        for pattern in ("quodeq.api.app", "quodeq.action_api", "quodeq dashboard"):
            try:
                subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                pass

        self._port = None
        self._browser_opened = False
        self._status_item.title = "Stopped"
        self._open_item.set_callback(None)
        self._open_item._menuitem.setEnabled_(False)
        self._start_item.set_callback(self._on_start)
        self._start_item._menuitem.setEnabled_(True)
        self._stop_item.set_callback(None)
        self._stop_item._menuitem.setEnabled_(False)


def main():
    _source_user_path()
    QuodeqApp().run()


if __name__ == "__main__":
    main()
