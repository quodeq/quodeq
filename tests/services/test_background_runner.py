"""Bounded ThreadBackgroundRunner.

The runner used to start one daemon thread per submit with no cap. It is now
at most DEFAULT_MAX_WORKERS on-demand workers fed by a bounded queue; a
submit that finds the queue full drops the task with a warning.
"""
from __future__ import annotations

import threading
from unittest.mock import patch

from quodeq.services.background import WORKER_THREAD_PREFIX, ThreadBackgroundRunner
from tests._timeouts import budget


class _Sink:
    """LogSink that records warning and debug lines."""

    def __init__(self):
        self.warnings: list[str] = []
        self.debugs: list[str] = []

    def warning(self, message):
        self.warnings.append(message)

    def debug(self, message):
        self.debugs.append(message)

    def info(self, message):
        pass

    def error(self, message):
        pass

    def success(self, message):
        pass


def _worker_snapshot() -> set[int]:
    """Idents of background-worker-* threads already alive before this test."""
    return {t.ident for t in threading.enumerate() if t.name.startswith(WORKER_THREAD_PREFIX)}


def _new_workers(before: set[int]) -> list[threading.Thread]:
    """background-worker-* threads that were not already alive in *before*.

    Other runners in the suite use the same name prefix, so filtering the
    prefix alone would also pick up threads this test never started.
    """
    return [
        t
        for t in threading.enumerate()
        if t.name.startswith(WORKER_THREAD_PREFIX) and t.ident not in before
    ]


def _join_new_workers(before: set[int]) -> None:
    # Workers exit on their own once the queue is empty, so joining them is
    # how a test knows every accepted task has finished.
    for thread in _new_workers(before):
        thread.join(budget(5))


def test_100_blocking_tasks_use_at_most_4_threads_and_drop_the_overflow():
    sink = _Sink()
    runner = ThreadBackgroundRunner(log=sink)
    gate = threading.Event()
    started = threading.Semaphore(0)
    ran: list[int] = []
    ran_lock = threading.Lock()

    def task():
        started.release()
        gate.wait(budget(10))
        with ran_lock:
            ran.append(1)

    before = _worker_snapshot()
    # Phase 1: occupy all four workers, so phase 2 fills the queue exactly.
    for _ in range(4):
        runner.submit(task, name="blocking")
    for _ in range(4):
        assert started.acquire(timeout=budget(5))
    for _ in range(96):
        runner.submit(task, name="blocking")
    peak = len(_new_workers(before))
    gate.set()
    _join_new_workers(before)

    assert peak <= 4
    assert len(ran) == 4 + 32
    assert len(sink.warnings) == 100 - 4 - 32
    assert "dropped task blocking" in sink.warnings[0]


def test_a_failing_task_is_logged_at_debug_and_the_next_task_still_runs():
    sink = _Sink()
    runner = ThreadBackgroundRunner(log=sink)
    after = threading.Event()
    before = _worker_snapshot()

    def boom():
        raise RuntimeError("boom")

    runner.submit(boom, name="boom")
    runner.submit(after.set, name="after")

    assert after.wait(budget(5))
    _join_new_workers(before)
    assert any("boom" in line for line in sink.debugs)


def test_idle_runner_holds_no_threads_and_a_later_submit_starts_a_worker():
    runner = ThreadBackgroundRunner()
    first, second = threading.Event(), threading.Event()
    before = _worker_snapshot()

    runner.submit(first.set, name="first")
    assert first.wait(budget(5))
    _join_new_workers(before)
    assert _new_workers(before) == []

    runner.submit(second.set, name="second")
    assert second.wait(budget(5))
    _join_new_workers(before)


def test_a_failed_thread_start_releases_its_slot_and_a_later_submit_still_runs():
    sink = _Sink()
    runner = ThreadBackgroundRunner(log=sink)
    before = _worker_snapshot()
    real_start = threading.Thread.start
    raised = threading.Event()

    def _fail_once_then_start(self):
        if not raised.is_set():
            raised.set()
            raise RuntimeError("can't start new thread")
        real_start(self)

    first, second = threading.Event(), threading.Event()

    with patch.object(threading.Thread, "start", _fail_once_then_start):
        runner.submit(first.set, name="first")

    # The failed start must not block or raise past submit(), and the
    # runner must not still think a worker is running for it.
    assert not first.wait(0.01)

    runner.submit(second.set, name="second")
    assert second.wait(budget(5))
    _join_new_workers(before)

    # The task queued before the failed start was not lost: a later,
    # successful worker still picks it up.
    assert first.is_set()
    assert any("failed to start" in line for line in sink.warnings)
