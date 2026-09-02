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

from quodeq.dashboard._api_health import ApiConfig
from quodeq.dashboard._config import DashboardConfig
from quodeq.dashboard._networking import _MAX_PORT_SCAN_TRIES, _allow_plaintext_http
from quodeq.dashboard._frozen import subprocess_cmd
from quodeq.dashboard._probes import ApiProbes, NativeShell
from quodeq.dashboard._process import _PROCESS_WAIT_TIMEOUT_S, _wait_for_process
from quodeq.shared.logging import log_success
from quodeq.shared.utils import IS_WIN32

_HTTP_SCHEME = "http"


def _guard_plaintext_http(
    host: str, allow_plaintext: bool | None = None, *, probes: ApiProbes | None = None,
) -> None:
    """Refuse plaintext HTTP to a non-local host unless explicitly opted in."""
    probes = probes or ApiProbes()
    if host in probes.local_hosts():
        return
    if _allow_plaintext_http(allow_plaintext):
        logging.getLogger(__name__).warning(
            "API traffic to %s uses plaintext HTTP; use a TLS reverse proxy for remote hosts", host,
        )
    else:
        raise RuntimeError(
            f"Plaintext HTTP to non-localhost host {host!r} is not allowed. "
            "Set QUODEQ_ALLOW_PLAINTEXT_HTTP=1 to explicitly opt in, "
            "or use a TLS reverse proxy."
        )


def _ensure_action_api(
    host: str,
    start_port: int,
    max_tries: int = _MAX_PORT_SCAN_TRIES,
    api_config: ApiConfig | None = None,
    *, probes: ApiProbes | None = None,
) -> tuple[str, subprocess.Popen | None]:
    probes = probes or ApiProbes()
    cfg = api_config or ApiConfig()
    _guard_plaintext_http(host, cfg.allow_plaintext, probes=probes)
    for port in range(start_port, start_port + max_tries):
        base_url = f"{_HTTP_SCHEME}://{host}:{port}"
        if probes.is_port_open(host, port):
            if probes.api_healthy(base_url):
                return base_url, None
            continue
        return probes.spawn(port, base_url, cfg)
    raise RuntimeError("Unable to find a free port for Action API.")


def _ensure_action_api_forced(
    host: str,
    port: int,
    static_dist: Path | None = None,
    evaluations_dir: str | None = None,
    *, probes: ApiProbes | None = None,
) -> tuple[str, subprocess.Popen | None]:
    probes = probes or ApiProbes()
    _guard_plaintext_http(host, probes=probes)
    base_url = f"http://{host}:{port}"
    if probes.is_port_open(host, port):
        if probes.api_healthy(base_url):
            return base_url, None
        raise RuntimeError(f"Port {port} on {host} is in use and not a healthy Action API.")
    return probes.spawn(
        port, base_url, ApiConfig(static_dist=static_dist, evaluations_dir=evaluations_dir),
    )


def _stop_children_for(action_api_process: subprocess.Popen | None) -> None:
    if action_api_process and action_api_process.poll() is None:
        action_api_process.terminate()
        try:
            action_api_process.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            action_api_process.kill()


def _make_tstp_handler(stop_children: typing.Callable) -> typing.Callable:
    def _handle_tstp(_signum, _frame) -> None:
        stop_children()
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
    return _handle_tstp


def _make_term_handler(stop_children: typing.Callable) -> typing.Callable:
    def _handle_term(_signum, _frame) -> None:
        # Without this the API child outlives a `kill`/logout of the dashboard
        # and keeps holding its port, so the next launch scans past it and the
        # orphan lingers until it's found by hand. Only KeyboardInterrupt and
        # SIGTSTP used to reach _stop_children.
        stop_children()
        sys.exit(0)
    return _handle_term


def _register_serve_signal_handlers(stop_children: typing.Callable) -> None:
    if hasattr(signal, "SIGTSTP"):
        signal.signal(signal.SIGTSTP, _make_tstp_handler(stop_children))
    signal.signal(signal.SIGTERM, _make_term_handler(stop_children))


def _serve_and_wait(
    action_api_url: str,
    action_api_process: subprocess.Popen | None,
    config: DashboardConfig,
    *, shell: NativeShell | None = None,
) -> None:
    """Open window or browser, register signal handlers, and block until exit."""
    log_success(f"Dashboard running at {action_api_url}")
    stop_children = lambda: _stop_children_for(action_api_process)  # noqa: E731
    _register_serve_signal_handlers(stop_children)

    if config.build.use_native and config.build.open_browser:
        _serve_native(action_api_url, action_api_process, stop_children, shell=shell)
    elif config.build.open_browser:
        webbrowser.open(action_api_url)
        _serve_blocking(action_api_process, stop_children)
    else:
        _serve_blocking(action_api_process, stop_children)


def _linux_webview_fallback(
    action_api_url: str, action_api_process: subprocess.Popen | None,
    shell: NativeShell, stop_children: typing.Callable, serve_blocking: typing.Callable,
) -> None:
    logging.getLogger(__name__).warning(
        "pywebview's Linux GTK+/WebKit backend is missing — "
        "falling back to opening the dashboard in your browser. "
        "Install 'python3-gi' and 'gir1.2-webkit2-4.1' (Debian/Ubuntu) "
        "or 'python3-gobject' + 'webkit2gtk4.1' (Fedora/Arch) to get the native window.",
    )
    shell.open_browser(action_api_url)
    serve_blocking(action_api_process, stop_children)


def _try_focus_existing_instance(instance, stop_children: typing.Callable) -> bool:
    """Return True when an existing window was focused (caller should stop);
    False when there is none reachable (caller should open a new window).

    Focus, not send_reload(action_api_url): stop_children (called by the
    caller after we return True) kills the API that URL names, so handing it
    to the running window would point it at a server about to die. It keeps
    the backend it already has. (The runner's pre-spawn hand-off normally
    catches this case before any API exists; this is the late-race fallback
    for an instance that appeared since.)
    """
    # Probe rather than acquire: the *window* process owns the reload socket,
    # because it is the only one that can act on a reload. Binding it here
    # would leave the child unable to bind, its listener dead, and every
    # relaunch's reload dropped into a socket nobody reads.
    if not instance.probe_existing():
        return False
    try:
        instance.send_focus()
    except (ConnectionRefusedError, OSError):
        # The instance answered the probe but died before the send. Fall
        # through and open our own window; its try_acquire clears the
        # now-stale socket.
        logging.getLogger(__name__).warning("Could not reach existing instance — opening new window")
        return False
    stop_children()
    return True


def _open_webview_log():
    # Route webview stderr to a log file (not DEVNULL) so a platform import
    # failure or GTK error is actually recoverable from ~/.quodeq/run/.
    webview_log_path = Path.home() / ".quodeq" / "run" / "webview.log"
    try:
        webview_log_path.parent.mkdir(parents=True, exist_ok=True)
        return webview_log_path.open("a", encoding="utf-8")
    except OSError:
        return subprocess.DEVNULL


def _serve_native(
    action_api_url: str,
    action_api_process: subprocess.Popen | None,
    stop_children: typing.Callable,
    *, shell: NativeShell | None = None,
    serve_blocking: typing.Callable[..., None] | None = None,
) -> None:
    """Open a PyWebView native window with single-instance support.

    On Linux, pywebview additionally needs a working GTK+/WebKit2GTK stack
    (python3-gi, gir1.2-webkit2-4.1) that isn't shipped with the pip wheel.
    When those bindings are missing we fall back to --browser mode instead
    of silently dying after spawning a webview subprocess that immediately
    crashes on import.
    """
    shell = shell or NativeShell()
    serve_blocking = serve_blocking or _serve_blocking

    if not shell.webview_importable():
        raise RuntimeError(
            "pywebview is not installed. "
            "Try reinstalling with 'pip install --upgrade quodeq' or use --browser."
        )

    if sys.platform.startswith("linux") and not shell.linux_backend_available():
        _linux_webview_fallback(action_api_url, action_api_process, shell, stop_children, serve_blocking)
        return

    instance = shell.make_instance()
    if _try_focus_existing_instance(instance, stop_children):
        return

    # Pass Flask PID so the webview process can kill it on window close.
    api_pid = str(action_api_process.pid) if action_api_process else ""
    webview_stderr = _open_webview_log()

    shell.spawn_window(
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
    serve_blocking(action_api_process, stop_children)


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
