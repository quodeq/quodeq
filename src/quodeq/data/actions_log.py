"""Append-only log of post-scan user actions, project-scoped.

Mirrors EventLogWriter but writes to project_dir/actions.jsonl. This log is
read by the projection engine to apply user actions (dismissals, etc.) onto
the per-run state stores.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

from quodeq.core.events.models import EVENT_MODEL_MAP, BaseEvent, EventType
from quodeq.core.utils.locking import get_file_lock


_logger = logging.getLogger(__name__)

ACTIONS_LOG_FILENAME = "actions.jsonl"


class ActionLogWriter:
    """Thread-safe append-only writer for project_dir/actions.jsonl."""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self.log_path = project_dir / ACTIONS_LOG_FILENAME
        project_dir.mkdir(parents=True, exist_ok=True)
        self._lock = get_file_lock()

    def emit(self, event: BaseEvent) -> None:
        try:
            with open(self.log_path, mode="a", encoding="utf-8") as f:
                self._lock.acquire(f)
                try:
                    f.write(event.model_dump_json() + "\n")
                    f.flush()
                finally:
                    self._lock.release(f)
        except Exception as e:
            _logger.error("Failed to emit %s to %s: %s", event.event_type, self.log_path, e)
            raise


def read_action_events(project_dir: Path) -> Iterator[BaseEvent]:
    """Yield typed events from project_dir/actions.jsonl. Skips malformed lines."""
    log_path = project_dir / ACTIONS_LOG_FILENAME
    if not log_path.is_file():
        return
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                event_type = EventType(data["event_type"])
                model_cls = EVENT_MODEL_MAP[event_type]
                yield model_cls.model_validate(data)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                _logger.warning("Skipping malformed actions.jsonl line: %s", e)
                continue
