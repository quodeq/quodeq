"""File-based rate-limit store for single-machine multi-worker setups."""
from __future__ import annotations

import json
import logging
import tempfile
import threading
from pathlib import Path

from quodeq.api._rate_limit_config import _rate_limit_max, _rate_limit_window

_logger = logging.getLogger(__name__)

_DEFAULT_PATH = str(Path(tempfile.gettempdir()) / "quodeq_rate_limits.json")


class FileRateLimitStore:
    """Rate-limit store backed by a JSON file.

    Suitable for single-machine multi-worker deployments where processes
    need to share rate-limit state without Redis.  Not recommended for
    high-throughput production use.
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
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, list[float]]) -> None:
        try:
            self._path.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            _logger.warning("Failed to write rate-limit file %s", self._path)

    def record(self, ip: str, now: float) -> None:
        """Record a request from *ip* at time *now*."""
        if not ip:
            return
        with self._lock:
            data = self._load()
            timestamps = data.get(ip, [])
            timestamps.append(now)
            data[ip] = [t for t in timestamps if now - t < self._window]
            self._save(data)

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit."""
        with self._lock:
            data = self._load()
            timestamps = [t for t in data.get(ip, []) if now - t < self._window]
            return len(timestamps) >= self._max_requests
