import unittest
from pathlib import Path
import json
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload, EventType
from quodeq.core.events.writer import EventLogWriter

class TestEventLog(unittest.TestCase):
    def setUp(self):
        self.test_log = Path("/tmp/quodeq_test_events.jsonl")
        if self.test_log.exists():
            self.test_log.unlink()
        self.writer = EventLogWriter(self.test_log)

    def tearDown(self):
        if self.test_log.exists():
            self.test_log.unlink()

    def test_emit_judgment_event(self):
        # 1. Create a payload
        payload = JudgmentPayload(
            practice_id="clean-arch-001",
            verdict="violation",
            dimension="Security",
            file="src/auth.py",
            line=42,
            reason="Hardcoded secret detected",
            title="Hardcoded Secret",
            confidence=95
        )

        # 2. Create the event
        event = JudgmentCreatedEvent(payload=payload)
        
        # 3. Emit the event
        self.writer.emit(event)

        # 4. Verify file exists and has content
        self.assertTrue(self.test_log.exists())
        self.assertGreater(self.test_log.stat().st_size, 0)

        # 5. Read back and verify JSON structure
        with open(self.test_log, "r") as f:
            line = f.readline()
            data = json.loads(line)

        self.assertEqual(data["event_type"], EventType.JUDGMENT_CREATED)
        self.assertEqual(data["payload"]["practice_id"], "clean-arch-001")
        self.assertEqual(data["payload"]["verdict"], "violation")
        self.assertEqual(data["payload"]["line"], 42)
        self.assertIn("event_id", data)
        self.assertIn("timestamp", data)

    def test_multiple_events_append(self):
        # Emit two events
        payload1 = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
        payload2 = JudgmentPayload(practice_id="p2", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")
        
        self.writer.emit(JudgmentCreatedEvent(payload=payload1))
        self.writer.emit(JudgmentCreatedEvent(payload=payload2))

        with open(self.test_log, "r") as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2)
        self.assertIn("p1", lines[0])
        self.assertIn("p2", lines[1])

def test_judgment_payload_accepts_req_field():
    p = JudgmentPayload(
        practice_id="M-ANA",
        verdict="violation",
        dimension="maintainability",
        file="foo.py",
        line=1,
        reason="too long",
        req="R-ANA-1",
    )
    assert p.req == "R-ANA-1"


def test_judgment_payload_req_defaults_to_none():
    p = JudgmentPayload(
        practice_id="M-ANA",
        verdict="violation",
        dimension="maintainability",
        file="foo.py",
        line=1,
        reason="too long",
    )
    assert p.req is None


if __name__ == "__main__":
    unittest.main()
