"""Event replay into the state store: full rebuild, incremental update, actions fold."""
from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from typing import Optional

from quodeq.core.dismissals import fold_dismissals
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
        store.clear_all()
        return self._project(event_log, store, since=None)

    def update(self, event_log: Path, run_dir: Path) -> int:
        """Incremental: replay only events after the stored checkpoint.

        Resumes from the stored byte offset (``get_projected_size``) so a
        call with few new events doesn't re-parse the whole file; ``since``
        stays as a belt-and-suspenders timestamp filter for the (rare) case
        the offset predates the checkpoint, e.g. a first-ever call where no
        offset was recorded yet.
        """
        store = self._store_factory(run_dir)
        current_size = event_log.stat().st_size if event_log.is_file() else 0
        from_offset = min(store.get_projected_size() or 0, current_size)
        return self._project(
            event_log, store,
            since=store.get_checkpoint(),
            from_offset=from_offset,
        )

    def update_actions(self, actions_log: Path, run_dir: Path, *, force: bool = False) -> int:
        """Apply the project's net dismissed state to run_dir's findings.

        ``actions.jsonl`` is folded into one ``DismissedKeys`` -- the same fold
        the services read side uses -- and every finding row's verdict is set
        from it. The pass is skipped while the log's size is unchanged since
        the last application, unless ``force=True`` (events.jsonl grew: the
        brand-new findings must be matched against existing dismissals).
        Returns the number of rows whose verdict changed.

        The fold replaces the older per-event replay: a fingerprinted entry
        supersedes the line-keyed entry of the same finding, which one UPDATE
        per event could never take back. One db connection for the whole
        pass; per-event connections made bulk dismiss/delete
        O(runs x events x connect) and froze the Overview.
        """
        from quodeq.data.actions_log import read_action_events  # noqa: PLC0415

        store = self._store_factory(run_dir)
        last_size = store.get_actions_projected_size() or 0
        current_size = actions_log.stat().st_size if actions_log.is_file() else 0

        if not force and current_size == last_size:
            return 0

        dismissed = fold_dismissals(read_action_events(actions_log.parent))
        with store.connection():
            changed = store.apply_dismissed_state(dismissed)
            store.save_actions_projected_size(current_size)
        return changed

    def _project(
        self,
        event_log: Path,
        store: SQLiteStateStore,
        *,
        since: Optional[datetime],
        from_offset: int = 0,
    ) -> int:
        size_before = event_log.stat().st_size
        reader = EventLogReader(event_log)
        count = 0
        last_ts = None
        conn_ctx = store.connection() if hasattr(store, "connection") else nullcontext()
        with conn_ctx:
            for event in reader.stream(since_timestamp=since, from_offset=from_offset):
                try:
                    handle(event, store)
                    last_ts = event.timestamp
                    count += 1
                except (ValueError, KeyError, TypeError):
                    # Same contract as _project_actions: a sqlite3.Error aborts
                    # the replay rather than being skipped as a bad event.
                    _logger.error(
                        "Handler failed for event %s (type=%s) - skipping",
                        event.event_id,
                        event.event_type,
                        exc_info=True,
                    )
            if last_ts is not None:
                store.save_checkpoint(last_ts)
                store.save_projected_size(size_before)
        _logger.info("Projected %d events from %s", count, event_log)
        return count
