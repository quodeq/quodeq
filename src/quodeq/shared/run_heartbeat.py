"""Per-run heartbeat thread.

Touches ``{run_dir}/.heartbeat`` every *interval* seconds. The file's
mtime is the liveness signal consumed by the dashboard's stale-detection
logic (separate module in Plan B).

Design: daemon thread so a Python interpreter exit during SIGKILL/power-
off does not prevent shutdown.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

_logger = logging.getLogger(__name__)

HEARTBEAT_FILENAME = ".heartbeat"


class HeartbeatThread:
    """Background thread that periodically updates run_dir/.heartbeat mtime."""

    def __init__(self, run_dir: Path, *, interval: float = 5.0) -> None:
        self._path = run_dir / HEARTBEAT_FILENAME
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # idempotent
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="quodeq-heartbeat", daemon=True)
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._path.touch()
            except OSError as exc:
                # Best-effort — disk issues surface via other paths.
                _logger.debug("heartbeat touch failed: %s", exc)
            self._stop.wait(self._interval)
