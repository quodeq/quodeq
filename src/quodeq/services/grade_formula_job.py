"""Grade-formula rescore off the request path.

PUT/DELETE /api/grade-formula used to rescore every run inside the request.
This module runs that pass in the background instead: one daemon worker,
woken by ``request()``. A request that lands mid-pass makes the worker drop
the pass at the next run boundary and start over with the params saved by
then, so any number of PUTs collapse into one pending restart and the last
write wins (the same rule as ``save_params``). Runs rewritten under older
params are redone by the restart. ``apply_to_all_runs`` clears the shared
dimension cache on every exit, and ``score_cache_version`` hashes the
params, so a read mid-pass never serves a stale-keyed cache.

Not a ``ThreadPoolExecutor``: its workers are non-daemon and would hold the
desktop window open on exit. Not ``ThreadBackgroundRunner`` either: that
swallows failures at debug level, and a failed pass must be visible (state
``error`` plus a warning). No logging import (SEP-06): failures go through
the injected ``LogSink``, with the traceback in the message because the sink
has no ``exc_info``. The worker starts on the first ``request()``, so
building one (every ``create_app``, every test app) costs no thread.

The owed pass is durable: ``request()`` writes a marker file beside the
params file and only a completed pass with nothing pending removes it (an
abort or an error keeps it). ``resume_pending()`` at app start requests a
pass when the marker is there, so quitting mid-pass does not leave runs on
the old formula for good.
"""
from __future__ import annotations

import enum
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from quodeq.core.observability import NULL_LOG, LogSink
from quodeq.services import grade_formula
from quodeq.shared.fault_isolation import run_isolated

WORKER_THREAD_NAME = "grade-formula-rescore"
# stop() waits this long for the worker. A pass checks for stop between runs,
# so this only has to cover one run's recompute plus its retries.
_STOP_JOIN_TIMEOUT_S = 10.0

ApplyFn = Callable[..., grade_formula.ApplyResult]


class RescoreState(enum.StrEnum):
    """Wire values of ``rescore.state`` (mirrored in ui/src/vocab/rescoreState.js).

    The grade-formula job's lifecycle. Not ``RescoreStatus``
    (``services/rescore_run.py``), which is one run's rescore outcome.
    """

    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


@dataclass(frozen=True)
class RescoreSnapshot:
    """Point-in-time view of the rescore job, as the API reports it."""

    state: RescoreState
    generation: int
    applied_generation: int
    done: int
    total: int
    failed: tuple[str, ...]

    def to_payload(self) -> dict:
        """The camelCase ``rescore`` object of the grade-formula responses."""
        return {
            "state": self.state.value,
            "generation": self.generation,
            "appliedGeneration": self.applied_generation,
            "done": self.done,
            "total": self.total,
            "failed": len(self.failed),
        }


class GradeFormulaRescorer:
    """One background worker that rescores every run with the saved params."""

    def __init__(self, apply_fn: ApplyFn | None = None, *, log: LogSink = NULL_LOG) -> None:
        # None resolves grade_formula.apply_to_all_runs at pass time, so a
        # monkeypatch on the module reaches an app-built rescorer too.
        self._apply_fn = apply_fn
        self._log = log
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._pending = False
        self._reports_root = Path()
        self._state = RescoreState.IDLE
        self._generation = 0
        self._applied_generation = 0
        self._done = 0
        self._total = 0
        self._failed: tuple[str, ...] = ()

    def request(self, reports_root: Path) -> RescoreSnapshot:
        """Ask for a pass over *reports_root* with the params saved now; returns at once."""
        with self._cond:
            self._write_marker_locked(grade_formula.mark_rescore_pending, "record")
            self._reports_root = reports_root
            self._generation += 1
            self._pending = True
            if self._state is not RescoreState.RUNNING:
                # A fresh pass: do not report the last pass's done/total.
                self._done = self._total = 0
            self._state = RescoreState.RUNNING
            self._ensure_worker_locked()
            self._cond.notify_all()
            return self._snapshot_locked()

    def resume_pending(self, reports_root: Path) -> RescoreSnapshot | None:
        """Request a pass when an earlier process left one owed; None (and no thread) otherwise."""
        if not grade_formula.rescore_pending():
            return None
        self._log.info("Resuming a grade-formula rescore pass left unfinished by the last run")
        return self.request(reports_root)

    def snapshot(self) -> RescoreSnapshot:
        """Current state, for GET /api/grade-formula."""
        with self._cond:
            return self._snapshot_locked()

    def wait_idle(self, timeout: float) -> bool:
        """Block until no pass is running or pending; False on timeout."""
        with self._cond:
            return self._cond.wait_for(lambda: self._state is not RescoreState.RUNNING, timeout)

    def stop(self) -> None:
        """Stop the worker at the next run boundary and join it. Terminal."""
        with self._cond:
            self._stopping = True
            thread, self._thread = self._thread, None
            self._cond.notify_all()
        if thread is not None:
            thread.join(_STOP_JOIN_TIMEOUT_S)

    def _snapshot_locked(self) -> RescoreSnapshot:
        return RescoreSnapshot(
            state=self._state,
            generation=self._generation,
            applied_generation=self._applied_generation,
            done=self._done,
            total=self._total,
            failed=self._failed,
        )

    def _ensure_worker_locked(self) -> None:
        if self._stopping or (self._thread is not None and self._thread.is_alive()):
            return
        thread = threading.Thread(target=self._worker, name=WORKER_THREAD_NAME, daemon=True)
        try:
            thread.start()
        except RuntimeError as exc:
            # The OS refused the thread. Nothing will run the pass, so say
            # so instead of reporting running forever; the marker stays, so
            # the next request or app start tries again.
            self._thread = None
            self._pending = False
            self._state = RescoreState.ERROR
            self._log.warning(f"Grade-formula rescore worker failed to start: {exc}")
            return
        self._thread = thread

    def _write_marker_locked(self, write: Callable[[], None], action: str) -> None:
        try:
            write()
        except OSError as exc:
            # The pass itself still runs; only resume-after-quit is lost.
            self._log.warning(f"Could not {action} the grade-formula rescore marker: {exc}")

    def _worker(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending or self._stopping)
                if self._stopping:
                    return
                self._pending = False
                generation, root = self._generation, self._reports_root
                self._done = self._total = 0
            run_isolated(
                lambda g=generation, r=root: self._run_pass(g, r),
                label=f"grade-formula rescore pass {generation}", log=self._log,
                on_error=lambda _exc: self._finish(RescoreState.ERROR),
            )

    def _run_pass(self, generation: int, root: Path) -> None:
        apply = self._apply_fn or grade_formula.apply_to_all_runs
        started = time.monotonic()
        result = apply(
            root, progress=self._on_progress,
            should_abort=lambda: self._superseded(generation),
        )
        if result.aborted:
            self._finish(RescoreState.IDLE)
            return
        self._log.info(
            f"Grade-formula rescore pass {generation}: {result.rescored} runs rescored, "
            f"{len(result.failed)} failed, {time.monotonic() - started:.1f}s"
        )
        self._finish(RescoreState.IDLE, generation=generation, failed=tuple(result.failed))

    def _finish(
        self, outcome: RescoreState, *, generation: int | None = None, failed: tuple[str, ...] = (),
    ) -> None:
        with self._cond:
            if generation is not None:
                self._applied_generation = generation
                self._failed = failed
                if not self._pending:
                    self._write_marker_locked(grade_formula.clear_rescore_pending, "clear")
            # A request that arrived during this pass is already pending: the
            # job is still running from the client's point of view.
            self._state = RescoreState.RUNNING if self._pending else outcome
            self._cond.notify_all()

    def _superseded(self, generation: int) -> bool:
        with self._cond:
            return self._stopping or self._generation != generation

    def _on_progress(self, done: int, total: int) -> None:
        with self._cond:
            self._done, self._total = done, total
