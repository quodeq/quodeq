"""Fire-and-forget background task submission, bounded.

Extracted so a route handler (``api/_evaluation_routes.py``'s salvage-scoring
GET) and a service-layer mutation flow (``services/mutation_rescore.py``'s
project-wide projection fallback) share one seam for "run this off the
current thread" instead of each spawning its own ``threading.Thread``.
Distinct from ``EvaluationDispatcher`` (``services/evaluation_mixin.py``),
which dispatches a whole evaluation subprocess; this is for small, in-process
work items that must not block the caller.

Bounded: at most ``max_workers`` daemon threads, fed by a
``queue.Queue(maxsize=max_queued)``, instead of one daemon thread per submit
with no cap (a burst of mutations used to grow the thread count without
limit). A submit that finds the queue full drops the task with a warning
instead of blocking the caller. Both callers tolerate a drop: salvage
scoring is claimed again by the next GET, and the projection fallback
already skips while a projection for the project is running. Workers start
on demand and exit as soon as the queue is empty, so an idle runner holds no
threads and tests or the CLI never leave one behind. Daemon threads, not
``ThreadPoolExecutor`` (its workers are non-daemon and would hold the
desktop window open on exit).
"""
from __future__ import annotations

import queue
import threading
from typing import Callable, Protocol

from quodeq.core.observability import NULL_LOG, LogSink

WORKER_THREAD_PREFIX = "background-worker-"
# Concurrency cap: enough to overlap a salvage score with a projection sweep
# or two, low enough that a burst of mutations cannot starve request threads.
DEFAULT_MAX_WORKERS = 4
# Waiting-task cap. Past it a burst is already far behind; dropping is cheaper
# than queueing work whose result nobody is waiting for.
DEFAULT_MAX_QUEUED = 32

_Task = tuple[Callable[[], None], str]


class BackgroundRunner(Protocol):
    """Abstraction for running a callable off the current thread."""

    def submit(self, fn: Callable[[], None], *, name: str = "") -> None:
        """Schedule *fn* to run in the background. Must never block/join."""
        ...


class ThreadBackgroundRunner:
    """Default runner: a bounded pool of on-demand daemon workers.

    Exceptions raised by *fn* are swallowed and logged at debug level: by
    the time the work runs, the caller has already returned its response (or,
    for the service-layer caller, already returned its own result), so there
    is no request left to report the failure to.
    """

    def __init__(
        self,
        *,
        log: LogSink = NULL_LOG,
        max_workers: int = DEFAULT_MAX_WORKERS,
        max_queued: int = DEFAULT_MAX_QUEUED,
    ) -> None:
        self._log = log
        self._max_workers = max_workers
        self._queue: queue.Queue[_Task] = queue.Queue(maxsize=max_queued)
        # Guards the queue hand-off and the live-worker count together, so a
        # worker deciding to exit on an empty queue and a submit deciding not
        # to spawn can never both happen around the same task.
        self._lock = threading.Lock()
        self._active = 0

    def submit(self, fn: Callable[[], None], *, name: str = "") -> None:
        """Queue *fn* for a worker and return at once; drop it with a warning when the queue is full."""
        spawn_id = None
        with self._lock:
            try:
                self._queue.put_nowait((fn, name))
            except queue.Full:
                accepted = False
            else:
                accepted = True
                spawn_id = self._reserve_worker_slot_locked()
        # Start the thread after releasing the lock: a new worker's first
        # move in _work() is to take the same lock, and starting it while
        # still holding it here would make that worker wait on us instead of
        # running -- exactly the moment a caller expects it to have already
        # picked up the task (e.g. a request thread checking that a mocked
        # collaborator was reached before it returns the response).
        if spawn_id is not None:
            threading.Thread(
                target=self._work, name=f"{WORKER_THREAD_PREFIX}{spawn_id}", daemon=True,
            ).start()
        if not accepted:
            self._log.warning(
                f"Background queue full ({self._queue.maxsize} waiting); dropped task {name or fn}"
            )

    def _reserve_worker_slot_locked(self) -> int | None:
        if self._active >= self._max_workers:
            return None
        self._active += 1
        return self._active

    def _work(self) -> None:
        while True:
            with self._lock:
                try:
                    fn, name = self._queue.get_nowait()
                except queue.Empty:
                    self._active -= 1
                    return
            self._run(fn, name)

    def _run(self, fn: Callable[[], None], name: str) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 -- background work must never crash the thread silently
            self._log.debug(f"Background task {name or fn} failed: {exc}")
