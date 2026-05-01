"""Server lifecycle — API startup, forced-port mode, and serve-and-wait loop."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import typing
import webbrowser
from pathlib import Path

from quodeq.dashboard._api_health import ApiConfig, action_api_healthy
from quodeq.dashboard._config import DashboardConfig
from quodeq.dashboard._networking import (
    _MAX_PORT_SCAN_TRIES,
    _allow_plaintext_http,
    _is_port_open,
    _local_hosts,
)
from quodeq.dashboard._frozen import subprocess_cmd
from quodeq.dashboard._process import (
    _PROCESS_WAIT_TIMEOUT_S,
    _spawn_and_wait_local,
    _wait_for_process,
)
from quodeq.shared.logging import log_success
from quodeq.shared.utils import IS_WIN32

_HTTP_SCHEME = "http"


def _ensure_action_api(
    host: str,
    start_port: int,
    max_tries: int = _MAX_PORT_SCAN_TRIES,
    api_config: ApiConfig | None = None,
) -> tuple[str, subprocess.Popen | None]:
    cfg = api_config or ApiConfig()
    if host not in _local_hosts():
        if _allow_plaintext_http(cfg.allow_plaintext):
            logging.getLogger(__name__).warning(
                "API traffic to %s uses plaintext HTTP; use a TLS reverse proxy for remote hosts", host,
            )
        else:
            raise RuntimeError(
                f"Plaintext HTTP to non-localhost host {host!r} is not allowed. "
                "Set QUODEQ_ALLOW_PLAINTEXT_HTTP=1 to explicitly opt in, "
                "or use a TLS reverse proxy."
            )
    for port in range(start_port, start_port + max_tries):
        base_url = f"{_HTTP_SCHEME}://{host}:{port}"
        if _is_port_open(host, port):
            if action_api_healthy(base_url):
                return base_url, None
            continue
        return _spawn_and_wait_local(port, base_url, cfg)
    raise RuntimeError("Unable to find a free port for Action API.")


def _ensure_action_api_forced(
    host: str,
    port: int,
    static_dist: Path | None = None,
    evaluations_dir: str | None = None,
) -> tuple[str, subprocess.Popen | None]:
    base_url = f"http://{host}:{port}"
    if _is_port_open(host, port):
        if action_api_healthy(base_url):
            return base_url, None
        raise RuntimeError(f"Port {port} on {host} is in use and not a healthy Action API.")
    return _spawn_and_wait_local(
        port, base_url, ApiConfig(static_dist=static_dist, evaluations_dir=evaluations_dir),
    )


def _serve_and_wait(
    action_api_url: str,
    action_api_process: subprocess.Popen | None,
    config: DashboardConfig,
) -> None:
    """Open window or browser, register signal handlers, and block until exit."""
    log_success(f"Dashboard running at {action_api_url}")

    def _stop_children() -> None:
        if action_api_process and action_api_process.poll() is None:
            action_api_process.terminate()
            try:
                action_api_process.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                action_api_process.kill()

    def _handle_tstp(_signum, _frame) -> None:
        _stop_children()
        # Ctrl+Z sends SIGTSTP to the whole foreground process group, so a
        # wrapper like `uv run quodeq dashboard` is also stopped at this
        # point. We're about to exit, but if we leave the wrapper in the
        # stopped state it will never notice our exit (a stopped process
        # can't reap children) and will linger as an orphan in `T` state
        # after the terminal closes. Resume the parent so it wakes up,
        # sees us exit, and tears itself down cleanly.
        try:
            os.kill(os.getppid(), signal.SIGCONT)
        except OSError:
            pass
        sys.exit(0)

    if hasattr(signal, "SIGTSTP"):
        signal.signal(signal.SIGTSTP, _handle_tstp)

    if config.build.use_native and config.build.open_browser:
        _serve_native(action_api_url, action_api_process, _stop_children)
    elif config.build.open_browser:
        webbrowser.open(action_api_url)
        _serve_blocking(action_api_process, _stop_children)
    else:
        _serve_blocking(action_api_process, _stop_children)


def _serve_native(
    action_api_url: str,
    action_api_process: subprocess.Popen | None,
    stop_children: typing.Callable,
) -> None:
    """Open a PyWebView native window with single-instance support.

    On Linux, pywebview additionally needs a working GTK+/WebKit2GTK stack
    (python3-gi, gir1.2-webkit2-4.1) that isn't shipped with the pip wheel.
    When those bindings are missing we fall back to --browser mode instead
    of silently dying after spawning a webview subprocess that immediately
    crashes on import.
    """
    try:
        import webview  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "pywebview is not installed. "
            "Try reinstalling with 'pip install --upgrade quodeq' or use --browser."
        )

    if sys.platform.startswith("linux") and not _linux_webview_backend_available():
        logging.getLogger(__name__).warning(
            "pywebview's Linux GTK+/WebKit backend is missing — "
            "falling back to opening the dashboard in your browser. "
            "Install 'python3-gi' and 'gir1.2-webkit2-4.1' (Debian/Ubuntu) "
            "or 'python3-gobject' + 'webkit2gtk4.1' (Fedora/Arch) to get the native window.",
        )
        webbrowser.open(action_api_url)
        _serve_blocking(action_api_process, stop_children)
        return

    from quodeq.dashboard._instance import InstanceController

    instance = InstanceController()

    if not instance.try_acquire():
        try:
            instance.send_reload(action_api_url)
        except (ConnectionRefusedError, OSError):
            logging.getLogger(__name__).warning("Could not reach existing instance — opening new window")
            instance.shutdown()
            instance = InstanceController()
            if not instance.try_acquire():
                stop_children()
                return
        else:
            stop_children()
            return

    # Pass Flask PID so the webview process can kill it on window close.
    api_pid = str(action_api_process.pid) if action_api_process else ""

    # Route webview stderr to a log file (not DEVNULL) so a platform import
    # failure or GTK error is actually recoverable from ~/.quodeq/run/.
    webview_log_path = Path.home() / ".quodeq" / "run" / "webview.log"
    try:
        webview_log_path.parent.mkdir(parents=True, exist_ok=True)
        webview_stderr = webview_log_path.open("a", encoding="utf-8")
    except OSError:
        webview_stderr = subprocess.DEVNULL

    subprocess.Popen(
        subprocess_cmd("webview", [action_api_url, str(instance.sock_path), api_pid]),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=webview_stderr,
    )

    # Block on the API process, not the webview. If the webview subprocess
    # crashes (missing platform bindings, GTK errors, etc.) the API survives
    # and the user can still reach the dashboard in their browser. Without
    # this block the whole `quodeq dashboard` command returned immediately
    # after spawning the detached webview child and the API was torn down.
    _serve_blocking(action_api_process, stop_children)


def _linux_webview_backend_available() -> bool:
    """Return True if pywebview's GTK backend can actually load on Linux.

    pywebview-on-Linux needs PyGObject + WebKit2GTK; neither is a pip
    dependency of the `pywebview` wheel. Importing the GTK backend is the
    only reliable probe — a successful `import webview` only proves the
    Python package installed, not that its Linux backend is usable.
    """
    try:
        import gi  # type: ignore[import-untyped]
        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2  # noqa: F401
        return True
    except (ImportError, ValueError):
        # ValueError: "Namespace WebKit2 not available"
        return False


# Public alias for cross-module use within the dashboard package
serve_and_wait = _serve_and_wait


def _serve_blocking(
    action_api_process: subprocess.Popen | None,
    stop_children: typing.Callable,
) -> None:
    """Block until process exits or keyboard interrupt (browser mode)."""
    try:
        if action_api_process:
            _wait_for_process(action_api_process)
        elif IS_WIN32:
            threading.Event().wait()
        else:
            signal.pause()
    except KeyboardInterrupt:
        pass
    finally:
        stop_children()
