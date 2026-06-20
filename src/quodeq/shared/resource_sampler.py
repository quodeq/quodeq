"""Periodic resource snapshots written to the run log.

The run process has died silently in the field at sustained load — no
stack trace, no crash report, no jetsam entry, just a clean stop on the
heartbeat thread at the same instant Ollama saw all sockets close. With
no in-process trail it's impossible to tell whether the death was OOM,
FD exhaustion, segfault, or external SIGKILL.

This sampler runs alongside the heartbeat and writes one line per
interval to the run log, capturing the obvious dimensions:

    [resources] elapsed=12m05s rss=523MB threads=11 fds=87 ollama=15384MB

The next death gives us the trajectory of those numbers leading up to
the silence. No new dependencies — uses ``ps`` and stdlib only.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

from quodeq.shared.logging import log_info

_DEFAULT_INTERVAL_S = 60.0
_PS_TIMEOUT_S = 2.0
_KB_PER_MB = 1024
_UNKNOWN = -1


def _self_rss_mb() -> int:
    """Resident set size of the current process in MB. Returns -1 on failure."""
    return _ps_rss_mb(os.getpid())


def _ollama_rss_mb() -> int:
    """RSS of the first ``ollama`` process (if any) in MB. 0 if not running."""
    try:
        out = subprocess.run(
            ["pgrep", "-x", "ollama"], capture_output=True, text=True,
            timeout=_PS_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _UNKNOWN
    if out.returncode != 0:
        return 0  # ollama not running — explicit zero, not unknown
    pids = [p for p in out.stdout.split() if p.isdigit()]
    if not pids:
        return 0
    return _ps_rss_mb(int(pids[0]))


def _ps_rss_mb(pid: int) -> int:
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True,
            timeout=_PS_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _UNKNOWN
    raw = out.stdout.strip()
    if not raw.isdigit():
        return _UNKNOWN
    return int(raw) // _KB_PER_MB


def _fd_count() -> int:
    """Open file descriptor count for this process. Returns -1 on failure."""
    for path in (f"/proc/{os.getpid()}/fd", "/dev/fd"):
        try:
            return len(os.listdir(path))
        except OSError:
            continue
    return _UNKNOWN


def _format(elapsed_s: float, rss_mb: int, threads: int, fds: int, ollama_mb: int) -> str:
    mins, secs = divmod(int(elapsed_s), 60)
    return (
        f"[resources] elapsed={mins}m{secs:02d}s "
        f"rss={rss_mb}MB threads={threads} fds={fds} ollama={ollama_mb}MB"
    )


class ResourceSampler:
    """Background thread that logs a resource snapshot every *interval*.

    Daemon thread so a hard-kill of the process doesn't block exit. The
    sampler is best-effort: any error inside the loop is swallowed, never
    raised, and the next tick tries again.
    """

    def __init__(self, *, interval_s: float = _DEFAULT_INTERVAL_S) -> None:
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # idempotent
        self._stop.clear()
        self._started_at = time.monotonic()
        self._thread = threading.Thread(
            target=self._loop, name="quodeq-resource-sampler", daemon=True,
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def sample_once(self) -> str:
        """Compute and return a snapshot line without logging it. Useful for tests."""
        elapsed = time.monotonic() - (self._started_at or time.monotonic())
        return _format(
            elapsed,
            _self_rss_mb(),
            threading.active_count(),
            _fd_count(),
            _ollama_rss_mb(),
        )

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                log_info(self.sample_once())
            except Exception:
                pass  # best-effort: never let observability kill the run
            self._stop.wait(self._interval)
