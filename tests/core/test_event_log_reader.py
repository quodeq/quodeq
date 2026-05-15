import unittest
from pathlib import Path
import json
import time
from datetime import datetime, timedelta, timezone
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload, EventType
from quodeq.core.events.writer import EventLogWriter
from quodeq.core.events.reader import EventLogReader

class TestEventLogReader(unittest.TestCase):
    def setUp(self):
        self.test_log = Path("/tmp/quodeq_reader_test.jsonl")
        if self.test_log.exists():
            self.test_log.unlink()
        self.writer = EventLogWriter(self.test_log)
        self.reader = EventLogReader(self.test_log)

    def tearDown(self):
        if self.test_log.exists():
            self.test_log.unlink()

    def test_stream_and_checkpoint(self):
        # 1. Create 3 events with distinct timestamps
        # Use a small sleep to ensure they aren't exactly the same
        
        payload1 = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
        event1 = JudgmentCreatedEvent(payload=payload1)
        self.writer.emit(event1)
        
        # Capture timestamp after first event
        ts_checkpoint = event1.timestamp
        
        time.sleep(0.1)
        
        payload2 = JudgmentPayload(practice_id="p2", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")
        event2 = JudgmentCreatedEvent(payload=payload2)
        self.writer.emit(event2)

        # 2. Test all streaming
        all_events = list(self.reader.stream())
        self.assertEqual(len(all_events), 2)

        # 3. Test checkpointing (since_timestamp)
        # We want only events strictly AFTER event1.
        # We use ts_checkpoint as the threshold.
        filtered_events = list(self.reader.stream(since_timestamp=ts_checkpoint))
        
        self.assertEqual(len(filtered_events), 1)
        self.assertEqual(filtered_events[0].payload.practice_id, "p2")

    def test_resilience_to_corruption(self):
        # 1. Write a valid event
        payload = JudgmentPayload(practice_id="good", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
        self.writer.emit(JudgmentCreatedEvent(payload=payload))

        # 2. Manually append a corrupt line to the file
        with open(self.test_log, "a") as f:
            f.write("NOT_A_JSON_LINE\n") # JSON error
            f.write('{"event_type": "INVALID_TYPE", "payload": {}}\n') # Enum error
            f.write('{"event_id": "not-a-uuid", "event_type": "JUDGMENT_CREATED", "payload": {}}\n') # Schema error

        # 3. Write another valid event
        payload2 = JudgmentPayload(practice_id="after_corruption", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")
        self.writer.emit(JudgmentCreatedEvent(payload=payload2))

        # 4. Verify reader still works and skips corrupt lines
        events = list(self.reader.stream())
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].payload.practice_id, "good")
        self.assertEqual(events[1].payload.practice_id, "after_corruption")

    def test_latest_timestamp(self):
        payload = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
        self.writer.emit(JudgmentCreatedEvent(payload=payload))
        
        latest = self.reader.get_latest_timestamp()
        self.assertIsNotNone(latest)
        self.assertIsInstance(latest, datetime)

if __name__ == "__main__":
    unittest.main()
