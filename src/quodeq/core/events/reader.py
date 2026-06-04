from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, List, Optional

from pydantic import ValidationError

from quodeq.core.events.models import BaseEvent, EVENT_MODEL_MAP


_logger = logging.getLogger(__name__)


class EventLogReader:
    """
    A streaming reader for the Quodeq Event Log (JSONL).
    
    Provides safe, memory-efficient iteration over events, with support 
    for checkpointing to enable incremental processing.
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def stream(self, since_timestamp: Optional[datetime] = None) -> Generator[BaseEvent, None, None]:
        """
        Iterate over events in the log.
        
        Args:
            since_timestamp: If provided, only yield events with a timestamp 
                             strictly greater than this value.
        
        Yields:
            An instance of a BaseEvent.
        """
        if not self.log_path.exists():
            _logger.warning(f"Event log file not found: {self.log_path}")
            return

        with open(self.log_path, mode="r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue

                try:
                    # 1. Parse as raw dict first to determine the type
                    raw_data = json.loads(line)
                    event_type_str = raw_data.get("event_type")
                    
                    if not event_type_str:
                        _logger.warning(f"Missing 'event_type' in {self.log_path} at line {line_num}")
                        continue
                    
                    # 2. Use the map to find the correct Pydantic model
                    # We must convert the string to the Enum member
                    from quodeq.core.events.models import EventType
                    event_type = EventType(event_type_str)
                    
                    model_cls = EVENT_MODEL_MAP.get(event_type)
                    if not model_cls:
                        _logger.warning(f"No model mapped for event type {event_type_str} in {self.log_path} at line {line_num}")
                        continue

                    # 3. Validate the full event against the specific model
                    event = model_cls.model_validate(raw_data)
                    
                    # 4. Checkpoint logic (using strict inequality)
                    if since_timestamp and event.timestamp <= since_timestamp:
                        continue

                    yield event

                except (ValueError, KeyError) as e:
                    # Handles invalid Enum values or missing keys in raw_data
                    _logger.error(f"Invalid event structure in {self.log_path} at line {line_num}: {e}")
                    continue
                except ValidationError as e:
                    _logger.error(f"Schema mismatch in {self.log_path} at line {line_num}: {e}")
                    continue
                except json.JSONDecodeError:
                    _logger.error(f"Malformed JSON in {self.log_path} at line {line_num}")
                    continue
                except Exception as e:
                    _logger.error(f"Unexpected error reading {self.log_path} at line {line_num}: {e}")
                    continue

    def read_all(self, since_timestamp: Optional[datetime] = None) -> List[BaseEvent]:
        """Convenience method to read all available events into a list."""
        return list(self.stream(since_timestamp=since_timestamp))

    def get_latest_timestamp(self) -> Optional[datetime]:
        """
        Scans the log to find the timestamp of the very last event.
        """
        last_ts = None
        try:
            for event in self.stream():
                last_ts = event.timestamp
        except Exception as e:
            _logger.error(f"Failed to retrieve latest timestamp from {self.log_path}: {e}")
        
        return last_ts

    def __repr__(self) -> str:
        return f"<EventLogReader(path={self.log_path})>"
