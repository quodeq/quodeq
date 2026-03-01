from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from codecompass.logging import log_info, log_success, log_warning
from codecompass.paths import resolve_path


@dataclass
class DashboardConfig:
    port: int
    reports_dir: Path
    static_dist: Path
    repo_root: Path
    open_browser: bool
    no_build: bool
    reinstall: bool
    reports_defaulted: bool = False
    api_host: str | None = None
    api_port: int | None = None
    api_forced: bool = False


def validate_paths(config: DashboardConfig) -> None:
    if not config.reports_dir.exists():
        if config.reports_defaulted:
            config.reports_dir.mkdir(parents=True, exist_ok=True)
        else:
            raise FileNotFoundError(
                "Reports directory not found. "
                "Run `mkdir -p <path>` or omit --evaluations to use the default."
            )
    if not (config.static_dist / "index.html").exists():
        raise FileNotFoundError("Static dist missing index.html. Run without --no-build to build.")


def _npm_install(path: Path) -> None:
    subprocess.run(["npm", "install"], cwd=str(path), check=True)


def _npm_build(path: Path) -> None:
    subprocess.run(["npm", "install"], cwd=str(path), check=True)
    subprocess.run(["npm", "run", "build"], cwd=str(path), check=True)


def _sources_newer_than_dist(web_root: Path, dist_index: Path) -> bool:
    """Return True if any tracked source file is newer than dist/index.html."""
    if not dist_index.exists():
        return True
    dist_mtime = dist_index.stat().st_mtime
    watch_dirs = [web_root / "src", web_root / "public"]
    watch_files = [web_root / "package.json", web_root / "vite.config.js"]
    for f in watch_files:
        if f.exists() and f.stat().st_mtime > dist_mtime:
            return True
    for d in watch_dirs:
        if not d.exists():
            continue
        for f in d.rglob("*"):
            if f.is_file() and f.stat().st_mtime > dist_mtime:
                return True
    return False


def _is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def _choose_ui_port(start: int, host: str = "127.0.0.1") -> int:
    port = start
    while _is_port_open(host, port):
        port += 1
    return port


def _choose_action_api_port(start: int = 8001, taken: set[int] | None = None) -> int:
    taken = taken or set()
    port = start
    while port in taken or _is_port_open("127.0.0.1", port):
        port += 1
    return port


def _spawn_action_api(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["CODECOMPASS_ACTION_API_PORT"] = str(port)
    env.setdefault("CODECOMPASS_ACTION_API_HOST", "127.0.0.1")
    return subprocess.Popen(
        [sys.executable, "-m", "codecompass.action_api"],
        env=env,
        start_new_session=True,
    )


def _wait_for_action_api(base_url: str, timeout_s: float = 10) -> None:
    deadline = time.monotonic() + timeout_s
    url = f"{base_url}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    payload = json.loads(response.read().decode("utf-8"))
                    if payload.get("ok") is True:
                        return None
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(0.2)
    raise TimeoutError(f"Action API did not become ready within {timeout_s} seconds.")


def _action_api_healthy(base_url: str) -> bool:
    url = f"{base_url}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("ok") is True
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def _ensure_action_api(host: str, start_port: int, max_tries: int = 20) -> tuple[str, subprocess.Popen | None]:
    port = start_port
    for _ in range(max_tries):
        base_url = f"http://{host}:{port}"
        if _is_port_open(host, port):
            if _action_api_healthy(base_url):
                return base_url, None
            port += 1
            continue
        process = _spawn_action_api(port)
        try:
            _wait_for_action_api(base_url)
        except Exception:
            if process.poll() is None:
                process.terminate()
                process.wait()
            raise
        return base_url, process
    raise RuntimeError("Unable to find a free port for Action API.")


def _ensure_action_api_forced(host: str, port: int) -> tuple[str, subprocess.Popen | None]:
    base_url = f"http://{host}:{port}"
    if _is_port_open(host, port):
        if _action_api_healthy(base_url):
            return base_url, None
        raise RuntimeError(f"Port {port} on {host} is in use and not a healthy Action API.")
    process = _spawn_action_api(port)
    try:
        _wait_for_action_api(base_url)
    except Exception:
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    return base_url, process


def _start_ui_server(config: DashboardConfig, action_api_url: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["CODECOMPASS_ACTION_API"] = action_api_url
    return subprocess.Popen(
        [
            "node",
            str(config.repo_root / "ui/server/src/index.js"),
            "--evaluations",
            str(config.reports_dir),
            "--repo-root",
            str(config.repo_root),
            "--static-dist",
            str(config.static_dist),
            "--port",
            str(config.port),
        ],
        env=env,
        start_new_session=True,
    )


def run_dashboard(config: DashboardConfig) -> int:
    reports_dir = resolve_path(str(config.reports_dir))
    static_dist = resolve_path(str(config.static_dist))
    repo_root = resolve_path(str(config.repo_root))

    requested_port = config.port
    chosen_port = _choose_ui_port(requested_port)
    if chosen_port != requested_port:
        log_warning(f"Port {requested_port} is in use. Using {chosen_port} instead.")
        config.port = chosen_port

    if config.reinstall or not (repo_root / "ui/server/node_modules").exists():
        log_info("Installing server dependencies (ui/server)...")
        _npm_install(repo_root / "ui/server")

    if not config.no_build:
        dist_index = static_dist / "index.html"
        if config.reinstall or _sources_newer_than_dist(repo_root / "ui/web", dist_index):
            log_info("Building web UI (ui/web)...")
            _npm_build(repo_root / "ui/web")
        else:
            log_info("Web UI is up to date, skipping build.")

    config = DashboardConfig(
        port=config.port,
        reports_dir=reports_dir,
        static_dist=static_dist,
        repo_root=repo_root,
        open_browser=config.open_browser,
        no_build=config.no_build,
        reinstall=config.reinstall,
        reports_defaulted=config.reports_defaulted,
        api_host=config.api_host,
        api_port=config.api_port,
        api_forced=config.api_forced,
    )

    validate_paths(config)

    log_info("Starting dashboard...")
    log_info(f"Reports: {config.reports_dir}")
    log_info(f"Static:  {config.static_dist}")
    log_info(f"Port:    {config.port}")

    action_api_host = config.api_host or "127.0.0.1"
    action_api_port = config.api_port or 8001
    if config.api_forced:
        action_api_url, action_api_process = _ensure_action_api_forced(action_api_host, action_api_port)
    else:
        action_api_url, action_api_process = _ensure_action_api(action_api_host, action_api_port)

    process = _start_ui_server(config, action_api_url)

    log_success(f"Dashboard running at http://localhost:{config.port}")

    if config.open_browser:
        webbrowser.open(f"http://localhost:{config.port}")

    current_action_api_process = action_api_process

    def _stop_children() -> None:
        for proc in (process, current_action_api_process):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def _handle_tstp(signum, frame) -> None:
        """Ctrl+Z: shut down cleanly instead of suspending."""
        _stop_children()
        sys.exit(0)

    signal.signal(signal.SIGTSTP, _handle_tstp)

    try:
        while process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            # Restart action API if it crashed
            if current_action_api_process and current_action_api_process.poll() is not None:
                if not _action_api_healthy(action_api_url):
                    log_warning("Action API stopped — restarting…")
                    try:
                        _, current_action_api_process = _ensure_action_api(
                            action_api_host, action_api_port
                        )
                        log_success("Action API restarted.")
                    except Exception as exc:
                        log_warning(f"Could not restart Action API: {exc}")
    except KeyboardInterrupt:
        pass
    finally:
        _stop_children()
