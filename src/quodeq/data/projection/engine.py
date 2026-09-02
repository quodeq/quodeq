from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Optional

from quodeq.data.events.reader import EventLogReader
from quodeq.data.projection.handlers import handle
from quodeq.data.sqlite.state_store import SQLiteStateStore

_logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Projects the JSONL event log into evaluation.db."""

    def __init__(
        self, store_factory: Callable[[Path], SQLiteStateStore] | None = None,
    ) -> None:
        self._store_factory = store_factory or SQLiteStateStore

    def rebuild(self, event_log: Path, run_dir: Path) -> int:
        """Full rebuild: clear all state and replay every event."""
        store = self._store_factory(run_dir)
        return self._project(event_log, store, since=None, _clear=True)

    def update(self, event_log: Path, run_dir: Path) -> int:
        """Incremental: replay only events after the stored checkpoint.

        Resumes from the stored byte offset (``get_projected_size``) so a
        call with few new events doesn't re-parse the whole file; ``since``
        stays as a belt-and-suspenders timestamp filter for the (rare) case
        the offset predates the checkpoint, e.g. a first-ever call where no
        offset was recorded yet.
        """
        store = self._store_factory(run_dir)
        return self._project(
            event_log, store,
            since=store.get_checkpoint(),
            from_offset=store.get_projected_size() or 0,
        )

    def update_actions(self, actions_log: Path, run_dir: Path, *, force: bool = False) -> int:
        """Replay actions.jsonl events into run_dir's state store.

        Incremental: the log is append-only, so when it merely grew we replay
        only the appended tail (from the last projected byte size). A full
        replay happens when ``force=True`` (events.jsonl grew — new findings
        must be matched against existing dismissals) or when the log shrank
        (rewritten/compacted). Handlers are idempotent (UPDATE by stable key),
        so a full replay is always safe.

        The whole replay holds ONE db connection; per-event connections made
        bulk dismiss/delete O(runs x events x connect) and froze the Overview.
        """
        from quodeq.data.actions_log import read_action_events  # noqa: PLC0415

        store = self._store_factory(run_dir)
        last_size = store.get_actions_projected_size() or 0
        current_size = actions_log.stat().st_size if actions_log.is_file() else 0

        if not force and current_size == last_size:
            return 0

        grew_only = not force and 0 < last_size < current_size
        offset = last_size if grew_only else 0

        applied = 0
        with store.connection():
            for event in read_action_events(actions_log.parent, from_offset=offset):
                try:
                    handle(event, store)
                    applied += 1
                except Exception:
                    _logger.error(
                        "Handler failed for action event %s (type=%s) - skipping",
                        getattr(event, "event_id", "?"),
                        getattr(event, "event_type", "?"),
                        exc_info=True,
                    )
            store.save_actions_projected_size(current_size)
        return applied

    def _project(
        self,
        event_log: Path,
        store: SQLiteStateStore,
        *,
        since: Optional[datetime],
        from_offset: int = 0,
        _clear: bool = False,
    ) -> int:
        reader = EventLogReader(event_log)
        count = 0
        last_ts = None
        with store.connection():
            if _clear:
                conn = store._held
                conn.execute("DELETE FROM findings")
                conn.execute("DELETE FROM dimension_scores")
                conn.execute(
                    "DELETE FROM run_meta WHERE key IN (?, ?, ?)",
                    ("projection_checkpoint", "projection_event_log_size", "actions_log_projected_size"),
                )
                conn.commit()
            for event in reader.stream(since_timestamp=since, from_offset=from_offset):
                try:
                    handle(event, store)
                    last_ts = event.timestamp
                    count += 1
                except (ValueError, KeyError, TypeError):
                    _logger.error(
                        "Handler failed for event %s (type=%s) - skipping",
                        event.event_id,
                        event.event_type,
                        exc_info=True,
                    )
            if last_ts is not None:
                store.save_checkpoint(last_ts)
                store.save_projected_size(event_log.stat().st_size)
        _logger.info("Projected %d events from %s", count, event_log)
        return count
