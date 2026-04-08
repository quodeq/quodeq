"""Action API subprocess spawning helpers."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from quodeq.shared.logging import log_warning
from quodeq.shared.utils import ACTION_API_MODULE, IS_WIN32 as _IS_WIN32, get_evaluations_dir

from quodeq.dashboard._api_health_check import wait_for_action_api

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


def spawn_action_api(
    port: int,
    pid_file_path: Path,
    default_host: str,
    api_config: ApiConfig | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    """Spawn the action API subprocess and record its PID."""
    cfg = api_config or ApiConfig()
    env = (env or os.environ).copy()
    env[_ENV_ACTION_API_PORT] = str(port)
    env.setdefault(_ENV_ACTION_API_HOST, default_host)
    if cfg.static_dist:
        env[_ENV_STATIC_DIST] = str(cfg.static_dist)
    env[_ENV_EVALUATIONS_DIR] = cfg.evaluations_dir or get_evaluations_dir()
    verbose = env.get("QUODEQ_VERBOSE") == "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", ACTION_API_MODULE],
        env=env,
        stdout=None if verbose else subprocess.DEVNULL,
        stderr=None if verbose else subprocess.DEVNULL,
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
