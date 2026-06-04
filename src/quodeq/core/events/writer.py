from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Union

from pydantic import BaseModel

from quodeq.core.events.models import BaseEvent
from quodeq.core.utils.locking import get_file_lock


_logger = logging.getLogger(__name__)


class EventLogWriter:
    """
    Thread-safe, append-only writer for the Quodeq Event Log (JSONL).
    
    This class is the sole authority for writing events to the immutable 
    source of truth in the Core layer.
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self._ensure_dir()
        self._lock = get_file_lock()

    def _ensure_dir(self) -> None:
        """Ensures the parent directory of the log file exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: BaseEvent) -> None:
        """
        Appends a single event to the JSONL log.
        
        Args:
            event: An instance of a BaseEvent (or subclass).
        """
        try:
            with open(self.log_path, mode="a", encoding="utf-8") as f:
                # Apply an exclusive lock on the file before writing.
                self._lock.acquire(f)
                try:
                    line = event.model_dump_json()
                    f.write(line + "\n")
                    f.flush()  # Ensure it hits the OS buffer
                finally:
                    # Release the lock.
                    self._lock.release(f)
        except Exception as e:
            _logger.error(f"Failed to emit event {event.event_id} to {self.log_path}: {e}")
            raise

    def __repr__(self) -> str:
        return f"<EventLogWriter(path={self.log_path})>"
