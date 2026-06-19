from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from quodeq.core.events.reader import EventLogReader
from quodeq.data.projection.handlers import handle
from quodeq.data.sqlite.state_store import SQLiteStateStore

_logger = logging.getLogger(__name__)


class ProjectionEngine:
    """Projects the JSONL event log into evaluation.db."""

    def rebuild(self, event_log: Path, run_dir: Path) -> int:
        """Full rebuild: clear all state and replay every event."""
        store = SQLiteStateStore(run_dir)
        store.clear_all()
        return self._project(event_log, store, since=None)

    def update(self, event_log: Path, run_dir: Path) -> int:
        """Incremental: replay only events after the stored checkpoint."""
        store = SQLiteStateStore(run_dir)
        return self._project(event_log, store, since=store.get_checkpoint())

    def update_actions(self, actions_log: Path, run_dir: Path, *, force: bool = False) -> int:
        """Replay actions.jsonl events into run_dir's state store.

        With ``force=False`` (default), skips when the actions log size hasn't
        changed since the last checkpoint. With ``force=True``, replays even if
        the size is unchanged -- needed when events.jsonl just grew, because new
        findings must be matched against existing dismissals.

        Handlers are idempotent (UPDATE by stable key), so full replay is safe.
        """
        from quodeq.data.actions_log import read_action_events  # noqa: PLC0415

        store = SQLiteStateStore(run_dir)
        last_size = store.get_actions_projected_size() or 0
        current_size = actions_log.stat().st_size if actions_log.is_file() else 0

        if not force and current_size == last_size:
            return 0

        applied = 0
        for event in read_action_events(actions_log.parent):
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
    ) -> int:
        reader = EventLogReader(event_log)
        count = 0
        last_ts = None
        for event in reader.stream(since_timestamp=since):
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
