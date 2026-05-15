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
            except Exception:
                _logger.error(
                    "Handler failed for event %s (type=%s) — skipping",
                    event.event_id,
                    event.event_type,
                    exc_info=True,
                )
        if last_ts is not None:
            store.save_checkpoint(last_ts)
        _logger.info("Projected %d events from %s", count, event_log)
        return count
