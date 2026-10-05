"""Background warm-up of per-project score caches at server boot.

After an upgrade invalidates the score caches, recomputing them takes minutes
per project. This engine runs that work on one daemon thread, newest project
activity first, through the single-flight ``cached_*`` helpers, so on-demand
requests dedupe against it and effectively jump the queue. The projects route
stays a pure read and re-enqueues anything still pending (self-healing), and
the Overview routes answer pending while the engine still owes their project
(``warmup_defer.defer_to_warmup``) instead of building it inline beside the
worker.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from quodeq.shared.fault_isolation import run_isolated

_logger = logging.getLogger(__name__)

_FAILURE_BACKOFF_S = 60.0
_SHUTDOWN_JOIN_TIMEOUT_S = 10  # bound on reset_for_tests' wait for the worker to exit


def _enumerate_projects(reports_dir: str) -> list[tuple[str, str]]:
    """Return [(project_id, latest_date_iso)] for every project directory."""
    from quodeq.services.wiring import list_runs, safe_read_dir  # noqa: PLC0415

    reports_root = Path(reports_dir)
    out: list[tuple[str, str]] = []
    for entry in safe_read_dir(reports_root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        runs = list_runs(reports_root, entry.name, limit=1)
        out.append((entry.name, (runs[0].date_iso or "") if runs else ""))
    return out


def _project_display_name(reports_dir: str, project_id: str) -> str:
    from quodeq.services.wiring import read_repository_info  # noqa: PLC0415

    info = read_repository_info(Path(reports_dir) / project_id) or {}
    return info.get("displayName") or info.get("name") or project_id


def warm_project(reports_dir: str, project_id: str, *, overview: bool = False) -> None:
    """Compute-and-cache one project's card summary and dashboard payload.

    What the engine does per queued project; callable inline for tests and
    budgets. The card goes through the single-flight read-through helper and
    the payload through the stamp memo, so this is a version-check no-op on
    a warm process and dedupes with on-demand requests.

    *overview* also pre-builds the latest Overview. Only the shared warm-up
    asks for it (a shared card appears once it is fully readable): the
    Overview lives in the per-process memo alone, so for local projects it
    would be rebuilt on every boot for projects nobody opens.
    """
    from quodeq.services.wiring import find_children  # noqa: PLC0415
    from quodeq.services._fs_metadata import warm_project_summary  # noqa: PLC0415
    from quodeq.services.scoring import get_project_scores  # noqa: PLC0415
    from quodeq.services import fs_reports  # noqa: PLC0415
    from quodeq.services.run_constants import LATEST_RUN  # noqa: PLC0415

    reports_root = Path(reports_dir)
    warm_project_summary(reports_root, project_id)
    # A parent's payload is never memoized (its stamp cannot see children),
    # so warming it would recompute on every boot for nothing. Skip.
    if find_children(reports_root, project_id):
        return
    get_project_scores(reports_root, project_id)
    if not overview:
        return
    # A run that vanished underneath is not a failure of the project: its
    # card and scores are cached by now.
    try:
        fs_reports.get_dashboard_overview(reports_dir, project_id, LATEST_RUN)
    except FileNotFoundError as exc:
        _logger.info("overview warm-up skipped for %s: %s", project_id, exc)


class WarmupEngine:
    """One daemon worker over an idempotent queue, with observable progress."""

    def __init__(
        self,
        warm_fn: Callable[[str, str], None] | None = None,
        list_fn: Callable[[str], list[tuple[str, str]]] | None = None,
    ) -> None:
        self._warm_fn = warm_fn or warm_project
        self._list_fn = list_fn or _enumerate_projects
        self._cond = threading.Condition()
        self._shutdown = threading.Event()
        self._pending: deque[str] = deque()
        self._queued: set[str] = set()
        self._failed_at: dict[str, float] = {}
        self._reports_dir: str | None = None
        self._thread: threading.Thread | None = None
        self._current: str | None = None
        self._current_name: str | None = None
        self._done = 0

    def start(self, reports_dir: str) -> None:
        """Queue every project under ``reports_dir`` and start the worker thread."""
        # Warming a disabled cache stores nothing, so it would be pure wasted
        # compute every boot; the inline read-through paths already handle
        # the kill switch themselves.
        from quodeq.shared.env import score_cache_disabled  # noqa: PLC0415

        if score_cache_disabled():
            return
        with self._cond:
            if self._thread is not None:
                return
            self._shutdown.clear()
            self._reports_dir = reports_dir
            try:
                listing = sorted(self._list_fn(reports_dir), key=lambda t: t[1], reverse=True)
            except (OSError, ValueError):
                _logger.warning("warm-up enumeration failed", exc_info=True)
                listing = []
            for project_id, _date in listing:
                if project_id not in self._queued:
                    self._queued.add(project_id)
                    self._pending.append(project_id)
            self._thread = threading.Thread(target=self._worker, name="score-warmup", daemon=True)
            self._thread.start()

    def enqueue(self, project_id: str) -> None:
        """Queue one project for warm-up (no-op before ``start`` or if already queued)."""
        with self._cond:
            if self._thread is None or project_id in self._queued:
                return
            failed = self._failed_at.get(project_id)
            if failed is not None and (time.monotonic() - failed) < _FAILURE_BACKOFF_S:
                return
            self._queued.add(project_id)
            self._pending.append(project_id)
            self._cond.notify()

    def prioritise(self, project_id: str) -> None:
        """Move a queued project to the head of the queue.

        The scores route calls this for the project on screen, so background
        warm-up of the other projects never runs ahead of it. A no-op before
        ``start``, for the project being warmed now, and for an id not queued.
        """
        with self._cond:
            if project_id == self._current or project_id not in self._pending:
                return
            self._pending.remove(project_id)
            self._pending.appendleft(project_id)

    def enqueue_pending(self, entries: list) -> None:
        """Re-enqueue every entry still marked ``summary_pending``.

        Self-healing: the projects route calls this on every page it
        returns, bounding the re-enqueue to page size instead of the full
        project count.
        """
        for entry in entries:
            if getattr(entry, "summary_pending", False):
                self.enqueue(entry.id)

    def owes(self, project_id: str) -> bool:
        """True while *project_id* is queued or being warmed, so its caches may still be cold."""
        with self._cond:
            return project_id == self._current or project_id in self._queued

    def current(self) -> str | None:
        """The project the worker is warming right now, or None while idle."""
        with self._cond:
            return self._current

    def failed(self, project_id: str) -> bool:
        """True when the last warm of *project_id* raised and no later warm succeeded."""
        with self._cond:
            return project_id in self._failed_at

    def generation(self) -> int:
        """How many projects the worker has finished; moves on every completion."""
        with self._cond:
            return self._done

    def snapshot(self) -> dict | None:
        """Return warm-up progress for the API, or None before ``start``."""
        with self._cond:
            if self._thread is None:
                return None
            in_flight = 1 if self._current is not None else 0
            return {
                "active": bool(self._pending) or in_flight == 1,
                "projectsDone": self._done,
                "projectsTotal": self._done + len(self._pending) + in_flight,
                "currentProjectName": self._current_name,
            }

    def stop(self) -> None:
        """Stop the worker and clear all queued state.

        The shared listing retires its engine this way when another clone is
        connected; tests use it through ``reset_for_tests``.
        """
        # Signal worker to shut down and wait for it to exit
        self._shutdown.set()
        thread_to_join = None
        with self._cond:
            thread_to_join = self._thread
            self._cond.notify()  # Wake up worker if it's waiting
        if thread_to_join is not None:
            thread_to_join.join(timeout=_SHUTDOWN_JOIN_TIMEOUT_S)
        # Clear all state after worker has stopped
        with self._cond:
            self._pending.clear()
            self._queued.clear()
            self._failed_at.clear()
            self._reports_dir = None
            self._thread = None
            self._current = None
            self._current_name = None
            self._done = 0

    def reset_for_tests(self) -> None:
        """Stop the worker and clear all queued state (test seam)."""
        self.stop()

    def _process_queued_item(self, project_id: str, reports_dir: str) -> None:
        """Resolve one queued project's display name and warm its caches.

        This is the sole statement ``run_isolated`` wraps in ``_worker``'s
        loop body: anything beyond the narrowed display-name fallback below
        (a bug in ``_project_display_name`` or a ``_warm_fn`` failure) must
        not kill the daemon thread, so it propagates for ``run_isolated`` to
        log with a traceback and absorb. Every path through here -- success,
        the narrowed fallback, or a re-raised failure -- still releases the
        item's queue/progress state in ``finally``.
        """
        try:
            # Fetch display name outside the lock (file I/O shouldn't block others)
            try:
                current_name = _project_display_name(reports_dir, project_id)
            except (OSError, ValueError):
                current_name = project_id
            with self._cond:
                self._current_name = current_name
            self._warm_fn(reports_dir, project_id)
            with self._cond:
                self._failed_at.pop(project_id, None)
        except Exception:
            with self._cond:
                self._failed_at[project_id] = time.monotonic()
            raise
        finally:
            with self._cond:
                self._queued.discard(project_id)
                self._current = None
                self._current_name = None
                self._done += 1

    def _worker(self) -> None:
        while True:
            with self._cond:
                # enqueue and reset_for_tests notify under the lock, so an idle
                # worker sleeps until there is work instead of polling.
                while not self._pending and not self._shutdown.is_set():
                    self._cond.wait()
                if self._shutdown.is_set():
                    break
                project_id = self._pending.popleft()
                self._current = project_id
                reports_dir = self._reports_dir or ""
            run_isolated(
                lambda: self._process_queued_item(project_id, reports_dir),
                label=f"score warmup for project {project_id!r}",
                log=_logger,
            )


engine = WarmupEngine()
