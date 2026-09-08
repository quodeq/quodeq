"""File-based rate-limit store for single-machine multi-worker setups."""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from quodeq.api._rate_limit_config import _rate_limit_max, _rate_limit_window, default_rate_limit_path
from quodeq.core.utils._file_lock import lock_file, unlock_file

_logger = logging.getLogger(__name__)

_DEFAULT_PATH = str(default_rate_limit_path())


class FileRateLimitStore:
    """Rate-limit store backed by a JSON file, with a short in-memory cache.

    Lets the workers of a single-machine deployment share rate-limit state
    through a common file without Redis. The ``threading.Lock`` below only
    serializes access within a SINGLE process; ``check_and_record()`` -- the
    actual enforcement path -- additionally takes a cross-process OS file
    lock (a ``.lock`` sidecar next to the data file, via ``_file_lock``) and
    reloads fresh from disk inside it, so concurrent worker processes cannot
    interleave the read-modify-write and cannot each act on a stale
    in-memory snapshot. ``record()``/``check()`` are not on the enforcement
    path and stay best-effort, cached, cross-process-racy by design.

    The in-memory cache (TTL ``_CACHE_TTL_S``) still governs ``record()``/
    ``check()``: another process's write may take up to ``_CACHE_TTL_S``
    seconds to become visible there, and an allowed request recorded
    in-memory but not yet flushed to disk is lost if this process is killed
    before the next flush.
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

    @contextmanager
    def _cross_process_lock(self) -> Iterator[None]:
        """Hold an exclusive OS lock on the ``.lock`` sidecar next to the
        data file. Locking the sidecar rather than the data file itself
        matters because _save() replaces the data file via os.replace() on
        every write, which would orphan a lock held on the old inode."""
        lock_path = self._path.with_suffix(self._path.suffix + ".lock")
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError:
            _logger.warning("Failed to create rate-limit dir %s", lock_path.parent)
        fd = os.open(str(lock_path), os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            lock_file(fd)
            yield
        finally:
            unlock_file(fd)
            os.close(fd)

    def check_and_record(self, ip: str, now: float) -> bool:
        """Same contract as check()+record(). This is the enforcement path,
        so it takes the cross-process OS lock and reloads fresh from disk
        for its decision instead of trusting the TTL cache -- a cached read
        would let two processes each act on their own stale snapshot within
        the same lock-free TTL window, even under a perfect file lock."""
        if not ip:
            return False
        with self._lock, self._cross_process_lock():
            data = self._load()
            timestamps = [t for t in data.get(ip, []) if now - t < self._window]
            limited = len(timestamps) >= self._max_requests
            if not limited:
                timestamps.append(now)
                data[ip] = timestamps
                self._save(data)
                self._last_flush = now
                self._dirty = False
            # Keep this process's fast path (record()/check()) warm with the
            # state we just confirmed on disk, win or lose.
            self._cache = data
            self._cache_loaded_at = now
            return limited
