"""Background warm-up of per-project score caches at server boot.

After an upgrade invalidates the score caches, recomputing them takes minutes
per project. This engine runs that work on one daemon thread, newest project
activity first, through the single-flight ``cached_*`` helpers, so on-demand
requests dedupe against it and effectively jump the queue. The projects route
stays a pure read and re-enqueues anything still pending (self-healing).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)

_FAILURE_BACKOFF_S = 60.0


def _enumerate_projects(reports_dir: str) -> list[tuple[str, str]]:
    """Return [(project_id, latest_date_iso)] for every project directory."""
    from quodeq.data.fs.report_parser.runs import list_runs, safe_read_dir  # noqa: PLC0415

    reports_root = Path(reports_dir)
    out: list[tuple[str, str]] = []
    for entry in safe_read_dir(reports_root):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        runs = list_runs(reports_root, entry.name, limit=1)
        out.append((entry.name, (runs[0].date_iso or "") if runs else ""))
    return out


def _project_display_name(reports_dir: str, project_id: str) -> str:
    from quodeq.services.ports import read_repository_info  # noqa: PLC0415

    info = read_repository_info(Path(reports_dir) / project_id) or {}
    return info.get("displayName") or info.get("name") or project_id


def _warm_project(reports_dir: str, project_id: str) -> None:
    """Compute-and-cache one project's summary and accumulated payloads.

    Both go through the single-flight read-through helpers, so this is a
    version-check no-op on a warm cache and dedupes with on-demand requests.
    """
    from quodeq.data.fs.children import find_children  # noqa: PLC0415
    from quodeq.services._fs_metadata import warm_project_summary  # noqa: PLC0415
    from quodeq.services.scoring import get_project_scores  # noqa: PLC0415

    reports_root = Path(reports_dir)
    warm_project_summary(reports_root, project_id)
    # Parents bypass the accumulated cache entirely (scoring/__init__.py),
    # so warming them would recompute on every boot for nothing. Skip.
    if not find_children(reports_root, project_id):
        get_project_scores(reports_root, project_id)


class WarmupEngine:
    """One daemon worker over an idempotent queue, with observable progress."""

    def __init__(
        self,
        warm_fn: Callable[[str, str], None] | None = None,
        list_fn: Callable[[str], list[tuple[str, str]]] | None = None,
    ) -> None:
        self._warm_fn = warm_fn or _warm_project
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
        # Warming a disabled cache stores nothing, so it would be pure wasted
        # compute every boot; the inline read-through paths already handle
        # the kill switch themselves.
        from quodeq.shared._env import score_cache_disabled  # noqa: PLC0415

        if score_cache_disabled():
            return
        with self._cond:
            if self._thread is not None:
                return
            self._shutdown.clear()
            self._reports_dir = reports_dir
            try:
                listing = sorted(self._list_fn(reports_dir), key=lambda t: t[1], reverse=True)
            except Exception:  # noqa: BLE001 - never block server start
                _logger.warning("warm-up enumeration failed", exc_info=True)
                listing = []
            for project_id, _date in listing:
                if project_id not in self._queued:
                    self._queued.add(project_id)
                    self._pending.append(project_id)
            self._thread = threading.Thread(target=self._worker, name="score-warmup", daemon=True)
            self._thread.start()

    def enqueue(self, project_id: str) -> None:
        with self._cond:
            if self._thread is None or project_id in self._queued:
                return
            failed = self._failed_at.get(project_id)
            if failed is not None and (time.monotonic() - failed) < _FAILURE_BACKOFF_S:
                return
            self._queued.add(project_id)
            self._pending.append(project_id)
            self._cond.notify()

    def snapshot(self) -> dict | None:
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

    def reset_for_tests(self) -> None:
        # Signal worker to shut down and wait for it to exit
        self._shutdown.set()
        thread_to_join = None
        with self._cond:
            thread_to_join = self._thread
            self._cond.notify()  # Wake up worker if it's waiting
        if thread_to_join is not None:
            thread_to_join.join(timeout=10)
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

    def _worker(self) -> None:
        while True:
            with self._cond:
                while not self._pending and not self._shutdown.is_set():
                    self._cond.wait(timeout=0.1)
                if self._shutdown.is_set():
                    break
                project_id = self._pending.popleft()
                self._current = project_id
                reports_dir = self._reports_dir or ""
            # Fetch display name outside the lock (file I/O shouldn't block others)
            try:
                current_name = _project_display_name(reports_dir, project_id)
            except Exception:  # noqa: BLE001 - bad metadata shouldn't crash worker
                current_name = project_id
            with self._cond:
                self._current_name = current_name
            try:
                self._warm_fn(reports_dir, project_id)
            except Exception:  # noqa: BLE001 - log and continue with the queue
                _logger.warning("warm-up failed for project %s", project_id, exc_info=True)
                with self._cond:
                    self._failed_at[project_id] = time.monotonic()
            finally:
                with self._cond:
                    self._queued.discard(project_id)
                    self._current = None
                    self._current_name = None
                    self._done += 1


engine = WarmupEngine()
