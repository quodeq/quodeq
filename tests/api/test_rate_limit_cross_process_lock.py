"""Cross-process locking for FileRateLimitStore.check_and_record().

Split out of test_rate_limit_hardening.py when that file crossed the
300-line cap; that file keeps the path/permission hardening, the env-config
parsing and the in-memory store's own regressions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from quodeq.api._rate_limit_file_store import FileRateLimitStore

# ---------------------------------------------------------------------------
# Cross-process locking for check_and_record()
# ---------------------------------------------------------------------------


def test_check_and_record_creates_lock_sidecar(tmp_path: Path):
    path = tmp_path / "rl.json"
    store = FileRateLimitStore(path=path, window=60.0, max_requests=5)
    store.check_and_record("1.2.3.4", 1000.0)
    assert (tmp_path / "rl.json.lock").exists()


def test_check_and_record_serializes_across_store_instances(tmp_path: Path):
    """Two FileRateLimitStore instances (simulating two worker processes)
    racing check_and_record() for the same IP at the same time must never
    let the combined allowed count exceed max_requests.

    Each instance has its own threading.Lock and its own in-memory cache,
    so nothing in-process serializes them against each other -- only the
    cross-process OS lock on the .lock sidecar can. Before that fix, a
    tight race lets both instances read "0 recorded" from disk and both
    allow, overshooting the limit.
    """
    import threading

    path = tmp_path / "rl.json"
    max_requests = 5
    n_threads = 40
    store_a = FileRateLimitStore(path=path, window=60.0, max_requests=max_requests)
    store_b = FileRateLimitStore(path=path, window=60.0, max_requests=max_requests)

    barrier = threading.Barrier(n_threads)
    allowed_count = 0
    count_lock = threading.Lock()

    def worker(store: FileRateLimitStore) -> None:
        nonlocal allowed_count
        barrier.wait()
        limited = store.check_and_record("1.2.3.4", 1000.0)
        if not limited:
            with count_lock:
                allowed_count += 1

    threads = [
        threading.Thread(target=worker, args=(store_a if i % 2 == 0 else store_b,))
        for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert allowed_count == max_requests, (
        f"expected exactly {max_requests} allowed requests out of {n_threads} racing "
        f"calls, got {allowed_count} -- the cross-process lock did not serialize the race"
    )


def test_cross_process_lock_does_not_unlock_or_leak_fd_on_timeout(tmp_path: Path):
    """If lock_file() times out (raises TimeoutError, having never acquired
    the lock), _cross_process_lock() must not call unlock_file() on the
    un-locked fd -- mirroring _queue_state.locked()'s locked_ok guard -- and
    must still close the fd so the timeout doesn't leak it.
    """
    from unittest.mock import patch

    import quodeq.api._rate_limit_file_store as store_mod

    path = tmp_path / "rl.json"
    store = FileRateLimitStore(path=path, window=60.0, max_requests=5)

    with patch.object(store_mod, "lock_file", side_effect=TimeoutError("locked out")) as lock_mock, \
         patch.object(store_mod, "unlock_file") as unlock_mock, \
         patch.object(store_mod.os, "close", wraps=store_mod.os.close) as close_mock:
        with pytest.raises(TimeoutError):
            with store._cross_process_lock():
                pytest.fail("must not yield when the lock was never acquired")

    lock_mock.assert_called_once()
    unlock_mock.assert_not_called()  # never locked -- must not unlock
    close_mock.assert_called_once()  # fd must still be closed, not leaked


def test_check_and_record_flushes_dirty_cache_before_reload(tmp_path: Path):
    """check_and_record() must not silently drop writes buffered by a prior
    record() call on the same instance that hadn't reached their flush TTL
    yet.

    Sequence: record("A", t0) does the first-ever flush (immediate, since
    _last_flush starts as None). record("A", t0+0.1), same TTL window,
    appends a second timestamp to the in-memory cache only -- dirty, not
    flushed. check_and_record("B", t0+0.15) on the SAME instance must flush
    that dirty cache before reloading from disk for its own decision;
    otherwise it reloads stale state (missing A's second timestamp), saves
    over it, and overwrites self._cache -- permanently losing A's second
    record from both disk and memory.
    """
    path = tmp_path / "rl.json"
    store = FileRateLimitStore(path=path, window=60.0, max_requests=100)

    store.record("A", 1000.0)
    store.record("A", 1000.1)  # same TTL window as above: buffered, not flushed
    assert store._dirty is True, "precondition: second record() must still be unflushed"

    limited = store.check_and_record("B", 1000.15)
    assert limited is False

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["A"] == [1000.0, 1000.1], "A's buffered second record must survive on disk"
    assert on_disk["B"] == [1000.15]

    assert store._cache["A"] == [1000.0, 1000.1], "A's buffered second record must survive in memory"
    assert store._cache["B"] == [1000.15]


# ---------------------------------------------------------------------------
# check_and_record() degrades instead of 500ing when the lock is unavailable
#
# _load()/_save() deliberately swallow OSError and degrade to best-effort.
# The cross-process lock did not: os.open() on an unwritable directory raises
# OSError and lock_file() raises TimeoutError under sustained contention, and
# both propagated through check_and_record() -> _check_rate_limit() -> the
# before_request hook, turning a degraded store into an HTTP 500 on every
# request.
# ---------------------------------------------------------------------------

def test_check_and_record_degrades_when_lock_times_out(tmp_path: Path, caplog):
    from unittest.mock import patch

    import quodeq.api._rate_limit_file_store as store_mod

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=5)

    with patch.object(store_mod, "lock_file", side_effect=TimeoutError("locked out")):
        limited = store.check_and_record("1.2.3.4", 1000.0)

    assert limited is False, "a lock timeout must not deny the request outright"
    # The decision is still made and recorded, just without cross-process
    # serialization, so the limit itself keeps working.
    assert store._cache["1.2.3.4"] == [1000.0]


def test_check_and_record_still_enforces_the_limit_while_degraded(tmp_path: Path):
    from unittest.mock import patch

    import quodeq.api._rate_limit_file_store as store_mod

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=2)

    with patch.object(store_mod, "lock_file", side_effect=TimeoutError("locked out")):
        assert store.check_and_record("1.2.3.4", 1000.0) is False
        assert store.check_and_record("1.2.3.4", 1000.1) is False
        assert store.check_and_record("1.2.3.4", 1000.2) is True


def test_check_and_record_degrades_when_lock_dir_is_unwritable(tmp_path: Path):
    """os.open() on the .lock sidecar fails on a read-only or missing dir."""
    from unittest.mock import patch

    import quodeq.api._rate_limit_file_store as store_mod

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=5)
    real_open = os.open

    def fail_on_lock_file(path, *args, **kwargs):
        if str(path).endswith(".lock"):
            raise OSError("read-only file system")
        return real_open(path, *args, **kwargs)

    with patch.object(store_mod.os, "open", side_effect=fail_on_lock_file):
        limited = store.check_and_record("1.2.3.4", 1000.0)

    assert limited is False
    assert store._cache["1.2.3.4"] == [1000.0]


def test_check_and_record_logs_a_warning_when_it_degrades(tmp_path: Path):
    from unittest.mock import patch

    import quodeq.api._rate_limit_file_store as store_mod

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=5)

    with patch.object(store_mod, "lock_file", side_effect=TimeoutError("locked out")), \
         patch.object(store_mod._logger, "warning") as warn:
        store.check_and_record("1.2.3.4", 1000.0)

    assert warn.called, "degrading silently would hide a broken rate-limit store"


def test_request_path_lock_timeout_is_short():
    """60s (the shared _file_lock default, sized for the subagent pool) would
    pin an HTTP worker thread for a minute under contention."""
    import quodeq.api._rate_limit_file_store as store_mod

    assert 0 < store_mod._LOCK_TIMEOUT_S <= 2.0


def test_lock_file_default_timeout_is_unchanged():
    """The rate limiter's short budget must be a per-call override, not a
    change to the shared primitive other workloads depend on."""
    from quodeq.core.utils import _file_lock

    assert _file_lock._UNIX_LOCK_TIMEOUT_S == 60.0
    assert _file_lock._WIN_LOCK_TIMEOUT_S == 60.0
