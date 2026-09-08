"""Hardening regression tests for the file rate-limit store (crit #94)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from quodeq.api._rate_limit_file_store import FileRateLimitStore
from quodeq.api._rate_limit_store import InMemoryRateLimitStore
from quodeq.api._rate_limit_factory import _validated_rate_limit_path, _DEFAULT_RATE_LIMIT_FILE

_skip_no_symlink = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink/POSIX-mode semantics differ on Windows"
)


@_skip_no_symlink
def test_save_does_not_follow_symlink(tmp_path: Path):
    sentinel = tmp_path / "victim.txt"
    sentinel.write_text("DO NOT TRUNCATE", encoding="utf-8")
    target = tmp_path / "quodeq_rate_limits.json"
    os.symlink(sentinel, target)  # attacker plants a symlink at the predictable name

    store = FileRateLimitStore(path=target)
    store.record("1.2.3.4", 1000.0)

    # The victim file the symlink pointed at is untouched ...
    assert sentinel.read_text(encoding="utf-8") == "DO NOT TRUNCATE"
    # ... and the target is now a real file holding our JSON, not a link.
    assert not target.is_symlink()
    assert "1.2.3.4" in json.loads(target.read_text(encoding="utf-8"))


@_skip_no_symlink
def test_save_writes_0600_permissions(tmp_path: Path):
    target = tmp_path / "rl.json"
    FileRateLimitStore(path=target).record("1.2.3.4", 1000.0)
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600


@_skip_no_symlink
def test_validated_path_rejects_symlink(tmp_path: Path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    os.symlink(real, link)
    assert _validated_rate_limit_path(str(link)) == _DEFAULT_RATE_LIMIT_FILE


# ---------------------------------------------------------------------------
# #81 -- dead path-traversal validation: ".." check ran on resolved path
# ---------------------------------------------------------------------------

def test_validated_path_rejects_dotdot_in_raw_path(tmp_path: Path):
    """A path containing '..' must fall back to default even if it resolves cleanly.

    Before the fix, ``".." in resolved.parts`` ran on the already-resolved path
    (where ``..`` has already been collapsed by ``Path.resolve()``), so inputs
    like ``/tmp/foo/../bar`` were incorrectly accepted.
    """
    # Build a path that contains ".." lexically but resolves to a real location.
    # /tmp/foo/../bar resolves to /tmp/bar, so resolved.parts has no "..".
    # The pre-fix code accepts this; the fixed code must reject it.
    raw = str(tmp_path / "subdir" / ".." / "rate_limits.json")
    assert ".." in Path(raw).parts, "precondition: '..' must be in raw parts"
    assert ".." not in Path(raw).resolve().parts, "precondition: resolve() removes '..'"
    assert _validated_rate_limit_path(raw) == _DEFAULT_RATE_LIMIT_FILE


# ---------------------------------------------------------------------------
# REL-082/083 -- window/max env values must be positive; zero, negative, or
# malformed values fall back to the defaults instead of disabling the limiter
# (window <= 0) or blocking every client (max <= 0).
# ---------------------------------------------------------------------------

from quodeq.api._rate_limit_config import (
    _DEFAULT_RATE_LIMIT_MAX,
    _DEFAULT_RATE_LIMIT_WINDOW,
    _rate_limit_max,
    _rate_limit_window,
)


@pytest.mark.parametrize("raw", ["0", "-5", "abc", ""])
def test_rate_limit_window_falls_back_on_invalid_env(raw):
    assert _rate_limit_window(env={"QUODEQ_RATE_LIMIT_WINDOW": raw}) == _DEFAULT_RATE_LIMIT_WINDOW


def test_rate_limit_window_accepts_valid_env():
    assert _rate_limit_window(env={"QUODEQ_RATE_LIMIT_WINDOW": "30"}) == 30


@pytest.mark.parametrize("raw", ["0", "-1", "many", ""])
def test_rate_limit_max_falls_back_on_invalid_env(raw):
    assert _rate_limit_max(env={"QUODEQ_RATE_LIMIT_MAX": raw}) == _DEFAULT_RATE_LIMIT_MAX


def test_rate_limit_max_accepts_valid_env():
    assert _rate_limit_max(env={"QUODEQ_RATE_LIMIT_MAX": "5"}) == 5


# ---------------------------------------------------------------------------
# REL-078 -- a valid-JSON-but-non-object state file must not crash
# record()/check(); it is treated as empty state.
# ---------------------------------------------------------------------------

def test_load_treats_non_dict_json_as_empty(tmp_path: Path):
    target = tmp_path / "rl.json"
    target.write_text("[1, 2, 3]", encoding="utf-8")
    store = FileRateLimitStore(path=target)
    assert store.check("1.2.3.4", 1000.0) is False
    store.record("1.2.3.4", 1000.0)  # must not raise
    assert "1.2.3.4" in json.loads(target.read_text(encoding="utf-8"))


def test_load_treats_scalar_json_as_empty(tmp_path: Path):
    target = tmp_path / "rl.json"
    target.write_text('"corrupt"', encoding="utf-8")
    store = FileRateLimitStore(path=target)
    assert store.check("1.2.3.4", 1000.0) is False


def test_file_store_check_and_record_does_one_load_one_save(tmp_path: Path):
    from unittest.mock import patch

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=5)

    with patch.object(store, "_load", wraps=store._load) as load_spy, \
         patch.object(store, "_save", wraps=store._save) as save_spy:
        limited = store.check_and_record("1.2.3.4", 1000.0)

    assert limited is False
    assert load_spy.call_count == 1
    assert save_spy.call_count == 1


def test_file_store_check_and_record_does_not_record_when_limited(tmp_path: Path):
    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=1)
    assert store.check_and_record("1.2.3.4", 1000.0) is False  # 1st request: allowed
    assert store.check_and_record("1.2.3.4", 1001.0) is True   # 2nd: limited, not recorded
    assert store.check_and_record("1.2.3.4", 1002.0) is True   # still limited (2nd wasn't recorded twice)


def test_record_and_check_cache_within_ttl_window(tmp_path: Path):
    """record()/check() are not on the enforcement path and keep the old
    TTL-cached behavior; check_and_record() no longer does (see the test
    below) since it must reload fresh from disk under the OS lock."""
    from unittest.mock import patch

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=100)

    with patch.object(store, "_load", wraps=store._load) as load_spy, \
         patch.object(store, "_save", wraps=store._save) as save_spy:
        for i in range(5):
            store.record("1.2.3.4", 1000.0 + i * 0.1)  # all within 0.4s
        assert store.check("1.2.3.4", 1000.4) is False

    assert load_spy.call_count == 1, f"expected 1 load for 5 calls inside the TTL window, got {load_spy.call_count}"
    assert save_spy.call_count == 1, f"expected 1 save for 5 calls inside the TTL window, got {save_spy.call_count}"


def test_check_and_record_bypasses_cache_and_reloads_every_call(tmp_path: Path):
    """check_and_record() is the enforcement path: it must reload fresh from
    disk every call rather than trust the TTL cache, even inside one TTL
    window, since two processes could otherwise each act on their own stale
    in-memory snapshot within the same lock-free window."""
    from unittest.mock import patch

    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=100)

    with patch.object(store, "_load", wraps=store._load) as load_spy:
        for i in range(5):
            limited = store.check_and_record("1.2.3.4", 1000.0 + i * 0.1)  # all within 0.4s
            assert limited is False

    assert load_spy.call_count == 5


def test_file_store_still_enforces_limit_within_a_single_ttl_window(tmp_path: Path):
    """Cache must not let a burst inside one TTL window slip past the limit --
    correctness is enforced from the in-memory write, not just the flush."""
    store = FileRateLimitStore(path=tmp_path / "rl.json", window=60.0, max_requests=2)
    assert store.check_and_record("1.2.3.4", 1000.0) is False   # 1st: allowed
    assert store.check_and_record("1.2.3.4", 1000.1) is False   # 2nd: allowed
    assert store.check_and_record("1.2.3.4", 1000.2) is True    # 3rd, same TTL window: limited


def test_file_store_flushes_immediately_once_limited(tmp_path: Path):
    """Once a client is actually rate-limited, that state must be durable right
    away -- only the "still allowed" path is allowed to batch writes."""
    import json

    path = tmp_path / "rl.json"
    store_a = FileRateLimitStore(path=path, window=60.0, max_requests=1)
    assert store_a.check_and_record("1.2.3.4", 1000.0) is False  # 1st: allowed, recorded

    # A second, independent store instance (simulating another worker process)
    # must see the durable state immediately after the limiting request, not
    # after waiting out the cache TTL.
    store_b = FileRateLimitStore(path=path, window=60.0, max_requests=1)
    assert store_b.check("1.2.3.4", 1000.05) is True


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


# ---------------------------------------------------------------------------
# InMemoryRateLimitStore.check_and_record() regression tests
# ---------------------------------------------------------------------------

def test_in_memory_store_check_and_record_empty_ip_guard():
    """Empty IP must not be recorded in the store."""
    store = InMemoryRateLimitStore(window=60.0, max_requests=5)
    # check_and_record with empty IP should return False but not record
    result = store.check_and_record("", 1000.0)
    assert result is False
    # Store should remain empty; no entry for empty string should exist
    assert "" not in store._store
    assert len(store._store) == 0


def test_in_memory_store_check_and_record_does_not_record_when_limited():
    store = InMemoryRateLimitStore(window=60.0, max_requests=1)
    assert store.check_and_record("1.2.3.4", 1000.0) is False  # 1st request: allowed
    assert store.check_and_record("1.2.3.4", 1001.0) is True   # 2nd: limited, not recorded
    assert store.check_and_record("1.2.3.4", 1002.0) is True   # still limited (2nd wasn't recorded twice)
