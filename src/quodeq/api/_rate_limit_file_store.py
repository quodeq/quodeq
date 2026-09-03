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
    """Rate-limit store backed by a JSON file, with a short in-memory cache.

    Lets the workers of a single-machine deployment share rate-limit state
    through a common file without Redis. NOTE: the ``threading.Lock`` below
    only serializes access within a SINGLE process; under multiple worker
    processes the file read-modify-write can still interleave, so the counts
    are best-effort (a concurrent burst may slip a few requests past the
    limit) rather than strictly exact across processes. Not recommended for
    high-throughput production use; add OS-level file locking
    (``fcntl.flock``) if exact cross-process enforcement is required.

    The in-memory cache (TTL ``_CACHE_TTL_S``) further widens that same
    best-effort window: another process's write may take up to
    ``_CACHE_TTL_S`` seconds to become visible here, and an allowed request
    recorded in-memory but not yet flushed to disk is lost if this process
    is killed before the next flush. Once a client is actually rate-limited
    that state is flushed immediately, so the "already limited" guarantee
    stays durable right away -- only the common allowed-request path batches
    disk writes.
    """

    _CACHE_TTL_S = 1.0

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
        self._cache: dict[str, list[float]] | None = None
        self._cache_loaded_at = 0.0
        # None means "never flushed yet" -- distinct from 0.0, which a caller
        # legitimately passes as `now` (several tests use a t=0 baseline).
        # Using 0.0 as the initial sentinel would make the first flush's
        # due-check (`now - self._last_flush >= self._CACHE_TTL_S`) evaluate
        # to False whenever the caller's first `now` is also near 0, silently
        # skipping the "always flush on cold start" guarantee.
        self._last_flush: float | None = None
        self._dirty = False

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

    def _cache_for(self, now: float) -> dict[str, list[float]]:
        """Return the in-memory cache, refilling from disk if stale. Caller
        must hold self._lock."""
        stale = self._cache is None or now - self._cache_loaded_at >= self._CACHE_TTL_S
        if stale:
            if self._cache is not None and self._dirty:
                # A reload discards self._cache and replaces it wholesale.
                # If it still holds writes from this process that were never
                # flushed (the flush TTL hadn't elapsed yet), persist them
                # first -- otherwise the reload silently drops them, even
                # with no crash involved. This keeps the "within-process
                # writes are never lost" guarantee independent of how the
                # reload TTL and the flush TTL happen to line up.
                self._save(self._cache)
                self._last_flush = now
                self._dirty = False
            self._cache = self._load()
            self._cache_loaded_at = now
        return self._cache

    def _flush(self, now: float, *, force: bool) -> None:
        """Persist the in-memory cache if forced or the flush TTL elapsed.
        Caller must hold self._lock."""
        if not self._dirty:
            return
        if force or self._last_flush is None or now - self._last_flush >= self._CACHE_TTL_S:
            self._save(self._cache)
            self._last_flush = now
            self._dirty = False

    def record(self, ip: str, now: float) -> None:
        """Record a request from *ip* at time *now*."""
        if not ip:
            return
        with self._lock:
            data = self._cache_for(now)
            timestamps = data.get(ip, [])
            timestamps.append(now)
            pruned = [t for t in timestamps if now - t < self._window]
            if pruned:
                data[ip] = pruned
            else:
                data.pop(ip, None)
            self._dirty = True
            self._flush(now, force=False)

    def check(self, ip: str, now: float) -> bool:
        """Return True if *ip* has exceeded the rate limit."""
        with self._lock:
            data = self._cache_for(now)
            timestamps = [t for t in data.get(ip, []) if now - t < self._window]
            return len(timestamps) >= self._max_requests

    def check_and_record(self, ip: str, now: float) -> bool:
        """Same contract as check()+record(), but one cache read + at most
        one disk round trip (fewer when the cache is warm)."""
        if not ip:
            return False
        with self._lock:
            data = self._cache_for(now)
            timestamps = [t for t in data.get(ip, []) if now - t < self._window]
            if len(timestamps) >= self._max_requests:
                return True
            timestamps.append(now)
            data[ip] = timestamps
            self._dirty = True
            # Force-flush the moment this IP becomes rate-limited so the
            # "limited" state is durable across processes right away; the
            # still-allowed path only flushes once the TTL elapses.
            just_limited = len(timestamps) >= self._max_requests
            self._flush(now, force=just_limited)
            return False
