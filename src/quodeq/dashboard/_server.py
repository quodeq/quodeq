"""Server lifecycle — API startup, forced-port mode, and serve-and-wait loop."""
from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
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
from quodeq.dashboard._process import (
    _PROCESS_WAIT_TIMEOUT_S,
    _spawn_and_wait_local,
    _wait_for_process,
)
from quodeq.shared.logging import log_success
from quodeq.shared.utils import IS_WIN32


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
        base_url = f"http://{host}:{port}"
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
    """Open browser, register signal handlers, and block until exit."""
    log_success(f"Dashboard running at {action_api_url}")

    if config.build.open_browser:
        webbrowser.open(action_api_url)

    def _stop_children() -> None:
        if action_api_process and action_api_process.poll() is None:
            action_api_process.terminate()
            try:
                action_api_process.wait(timeout=_PROCESS_WAIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                action_api_process.kill()

    def _handle_tstp(_signum, _frame) -> None:
        _stop_children()
        sys.exit(0)

    if hasattr(signal, "SIGTSTP"):
        signal.signal(signal.SIGTSTP, _handle_tstp)

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
        _stop_children()
