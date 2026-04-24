"""Subprocess spawning, heartbeat monitoring, and error handling."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from quodeq.analysis._config import AnalysisConfig, _SpawnPaths
from quodeq.analysis.errors import ProviderError
from quodeq.analysis.stream.progress_reader import _IncrementalProgressReader
from quodeq.shared import cancellation
from quodeq.shared.logging import log_warning
from quodeq.shared.utils import sanitize_sensitive as _sanitize_stderr

_TERMINATE_TIMEOUT_S = 10
_KILL_WAIT_TIMEOUT_S = 5


class AnalysisError(ProviderError):
    """Raised when the AI CLI subprocess fails (non-zero exit, auth error, etc.)."""


def _kill_tree(pid: int, sig: int = signal.SIGTERM) -> None:
    """Kill a process and all its children, cross-platform."""
    if sys.platform == "win32":
        # taskkill /T kills the entire process tree
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, timeout=_TERMINATE_TIMEOUT_S,
        )
    else:
        try:
            os.killpg(os.getpgid(pid), sig)
        except (ProcessLookupError, OSError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, OSError):
                pass


def _terminate_process(process: subprocess.Popen) -> None:
    """Kill the process and its entire process tree to prevent orphans."""
    _kill_tree(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=_TERMINATE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _kill_tree(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
        try:
            process.wait(timeout=_KILL_WAIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            process.kill()


def _run_with_heartbeat(
    process: subprocess.Popen,
    config: AnalysisConfig,
    stream_file: Path,
) -> bool:
    """Wait for process to finish, emitting heartbeat callbacks at intervals.

    Terminates the process if *max_duration* seconds elapse.
    Returns True if the process was terminated due to timeout.
    """
    elapsed = 0
    timed_out = False
    reader = _IncrementalProgressReader(stream_file, config.jsonl_file)

    while process.poll() is None:
        try:
            process.wait(timeout=config.heartbeat_interval)
        except subprocess.TimeoutExpired:
            if cancellation.is_cancelled():
                _terminate_process(process)
                return timed_out
            elapsed += config.heartbeat_interval
            if config.heartbeat_callback:
                config.heartbeat_callback(elapsed, reader.read_progress())
            if config.max_duration is not None and elapsed >= config.max_duration:
                log_warning(
                    f"Analysis exceeded max duration ({config.max_duration}s) "
                    f"-- terminating. Increase with --max-duration or QUODEQ_MAX_DURATION env var."
                )
                _terminate_process(process)
                timed_out = True
    return timed_out


def _check_process_result(process: subprocess.Popen, stream_err: Path) -> None:
    """Raise AnalysisError if the process exited with a non-zero code."""
    if process.returncode != 0:
        stderr_text = ""
        if stream_err.exists():
            try:
                stderr_text = _sanitize_stderr(stream_err.read_text().strip())
            except (OSError, UnicodeDecodeError):
                stderr_text = "(stderr unreadable)"
        raise AnalysisError(
            f"AI CLI exited with code {process.returncode}"
            + (f": {stderr_text}" if stderr_text else "")
        )


def _spawn_and_monitor(
    args: list[str], work_dir: Path, env: dict,
    paths: _SpawnPaths, cfg: AnalysisConfig,
) -> tuple[subprocess.Popen, bool]:
    """Spawn the AI CLI process, monitor with heartbeat, return (process, timed_out)."""
    with open(paths.stream_file, "w") as out, open(paths.stream_err, "w") as err:
        # start_new_session creates a new process group so we can kill the
        # entire tree (including child processes) when the agent is cancelled.
        process = subprocess.Popen(
            args, cwd=str(work_dir), env=env,
            stdout=out, stderr=err, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        timed_out = _run_with_heartbeat(process, cfg, paths.stream_file)
    return process, timed_out
