"""Action API spawning and health-check helpers.

Extracted from runner.py to keep that module under 300 lines.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from quodeq.shared.logging import log_warning
from quodeq.shared.utils import ACTION_API_MODULE, IS_WIN32 as _IS_WIN32

_HEALTH_CHECK_TIMEOUT_S = 0.5
_HEALTH_POLL_INTERVAL_S = 0.2
_DEFAULT_WAIT_TIMEOUT_S = 10

_ENV_ACTION_API_PORT = "QUODEQ_ACTION_API_PORT"
_ENV_ACTION_API_HOST = "QUODEQ_ACTION_API_HOST"
_ENV_STATIC_DIST = "QUODEQ_STATIC_DIST"
_ENV_EVALUATIONS_DIR = "QUODEQ_EVALUATIONS_DIR"


@dataclass(frozen=True)
class ApiConfig:
    """Grouping of optional API configuration paths and flags."""

    static_dist: Path | None = None
    evaluations_dir: str | None = None
    allow_plaintext: bool | None = None


def _popen_platform_kwargs() -> dict:
    """Return platform-specific Popen kwargs for process group isolation."""
    if _IS_WIN32:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def action_api_healthy(base_url: str) -> bool:
    """Return True if the action API at *base_url* responds healthy."""
    url = f"{base_url}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=_HEALTH_CHECK_TIMEOUT_S) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("ok") is True
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return False


def wait_for_action_api(base_url: str, timeout_s: float = _DEFAULT_WAIT_TIMEOUT_S) -> None:
    """Block until the action API becomes healthy, or raise TimeoutError."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if action_api_healthy(base_url):
            return None
        time.sleep(_HEALTH_POLL_INTERVAL_S)
    raise TimeoutError(f"Action API did not become ready within {timeout_s} seconds.")


def spawn_action_api(
    port: int,
    pid_file_path: Path,
    default_host: str,
    api_config: ApiConfig | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    """Spawn the action API subprocess and record its PID.

    The ``get_evaluations_dir`` import is deferred to avoid a circular
    dependency between ``dashboard._api_health`` and ``shared.utils``
    (which imports logging, which may trigger dashboard config loading).
    """
    from quodeq.shared.utils import get_evaluations_dir

    cfg = api_config or ApiConfig()
    env = (env or os.environ).copy()
    env[_ENV_ACTION_API_PORT] = str(port)
    env.setdefault(_ENV_ACTION_API_HOST, default_host)
    if cfg.static_dist:
        env[_ENV_STATIC_DIST] = str(cfg.static_dist)
    env[_ENV_EVALUATIONS_DIR] = cfg.evaluations_dir or get_evaluations_dir()
    proc = subprocess.Popen(
        [sys.executable, "-m", ACTION_API_MODULE],
        env=env,
        **_popen_platform_kwargs(),
    )
    try:
        pid_file_path.write_text(str(proc.pid))
    except (OSError, AttributeError) as exc:
        log_warning(f"Could not write PID file: {exc}")
    return proc


def spawn_and_wait(
    port: int,
    base_url: str,
    pid_file_path: Path,
    default_host: str,
    api_config: ApiConfig | None = None,
) -> tuple[str, subprocess.Popen]:
    """Spawn the action API on *port* and wait for it to become healthy."""
    process = spawn_action_api(port, pid_file_path, default_host, api_config)
    try:
        wait_for_action_api(base_url)
    except (subprocess.TimeoutExpired, OSError, TimeoutError):
        if process.poll() is None:
            process.terminate()
            process.wait()
        raise
    return base_url, process
