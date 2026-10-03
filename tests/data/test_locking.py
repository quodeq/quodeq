"""The whole-file lock the JSONL writers share has a deadline.

A second writer waiting on a held lock gives up with an ``OSError`` after the
``core/utils/file_lock.py`` budget instead of blocking forever; the writers'
callers already handle ``OSError`` from the append.
"""
from __future__ import annotations

import sys
import threading

from quodeq.core.utils import file_lock as file_lock_impl
from quodeq.data.locking import get_file_lock
from tests._timeouts import budget


def test_a_second_acquire_on_a_held_lock_gives_up_instead_of_hanging(tmp_path, monkeypatch):
    monkeypatch.setattr(file_lock_impl, "_LOCK_TIMEOUT_S", 0.2)
    path = tmp_path / "events.jsonl"
    path.write_text("", encoding="utf-8")
    lock = get_file_lock()
    held = threading.Event()
    release = threading.Event()
    outcome: list = []

    def holder() -> None:
        with open(path, "a", encoding="utf-8") as f:
            lock.acquire(f)
            held.set()
            release.wait(budget(30))
            lock.release(f)

    def contender() -> None:
        with open(path, "a", encoding="utf-8") as f:
            try:
                lock.acquire(f)
            except OSError as exc:
                outcome.append(exc)
                return
            outcome.append(None)
            lock.release(f)

    holder_thread = threading.Thread(target=holder, daemon=True)
    contender_thread = threading.Thread(target=contender, daemon=True)
    holder_thread.start()
    assert held.wait(budget(10))
    contender_thread.start()
    contender_thread.join(budget(10))
    still_waiting = contender_thread.is_alive()
    release.set()
    holder_thread.join(budget(10))
    contender_thread.join(budget(10))

    assert not still_waiting, "the second acquire blocked past the lock budget"
    (err,) = outcome
    assert isinstance(err, OSError)
    if sys.platform != "win32":
        assert isinstance(err, TimeoutError)
