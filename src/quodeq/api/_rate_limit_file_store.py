"""File-based rate-limit store for single-machine multi-worker setups."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from quodeq.api._rate_limit_config import _rate_limit_max, _rate_limit_window, default_rate_limit_path

_logger = logging.getLogger(__name__)

_DEFAULT_PATH = str(default_rate_limit_path())


class FileRateLimitStore:
    """Rate-limit store backed by a JSON file.

    Lets the workers of a single-machine deployment share rate-limit state
    through a common file without Redis. NOTE: the ``threading.Lock`` below
    only serializes access within a SINGLE process; under multiple worker
    processes the file read-modify-write can still interleave, so the counts
    are best-effort (a concurrent burst may slip a few requests past the
    limit) rather than strictly exact across processes. Not recommended for
    high-throughput production use; add OS-level file locking
    (``fcntl.flock``) if exact cross-process enforcement is required.
    """

    def __init__(
        self,
        path: str | Path = _DEFAULT_PATH,
        window: float | None = None,
        max_requests: int | None = None,
    ) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._window = window if window is not None else _rate_limit_window()
        self._max_requests = max_requests if max_requests is not None else _rate_limit_max()

    def _load(self) -> dict[str, list[float]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        # The state file is plain user-writable JSON; a valid non-object value
        # (array, scalar) would crash record()/check() at data.get(...).
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, list[float]]) -> None:
        parent = self._path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            _logger.warning("Failed to create rate-limit dir %s", parent)
            return
        # Write a fresh temp file then os.replace() onto the target. If an
        # attacker planted a symlink at self._path, the rename replaces the
        # link itself with our regular file and never truncates its target.
        payload = json.dumps(data).encode("utf-8")
        tmp_fd, tmp_name = tempfile.mkstemp(dir=parent, prefix=".rl-", suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "wb") as fh:
                fh.write(payload)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self._path)
        except OSError:
            _logger.warning("Failed to write rate-limit file %s", self._path)
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

    def record(self, ip: str, now: float) -> None:
        """Record a request from *ip* at time *now*."""
        if not ip:
            return
        with self._lock:
            data = self._load()
            timestamps = data.get(ip, [])
            timestamps.append(now)
            pruned = [t for t in timestamps if now - t < self._window]
            if pruned:
                data[ip] = pruned
            else:
                data.pop(ip, None)
            self._save(data)

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit."""
        with self._lock:
            data = self._load()
            timestamps = [t for t in data.get(ip, []) if now - t < self._window]
            return len(timestamps) >= self._max_requests
