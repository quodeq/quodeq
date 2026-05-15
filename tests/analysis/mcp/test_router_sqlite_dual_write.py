"""Tests for FindingsRouter event log emission (replaces old SQLite dual-write tests)."""
import io
from pathlib import Path

from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.core.events.reader import EventLogReader
from quodeq.core.events.writer import EventLogWriter
from quodeq.core.events.models import EventType


def _args(p="P1", file="x.py", line=1, t="violation"):
    return {"p": p, "file": file, "line": line, "t": t,
            "severity": "medium", "d": "dim", "reason": "r",
            "snippet": "s", "w": "title"}


def test_router_writes_jsonl_and_event_log(tmp_path: Path):
    fh = io.StringIO()
    event_log = EventLogWriter(tmp_path / "events.jsonl")
    router = FindingsRouter(fh, event_log=event_log)

    msg, dup = router.receive(_args())
    assert dup is False
    assert "Finding #1 recorded." in msg

    # JSONL written
    assert fh.getvalue().count("\n") == 1
    # Event log written
    events = EventLogReader(tmp_path / "events.jsonl").read_all()
    assert len(events) == 1
    assert events[0].event_type == EventType.JUDGMENT_CREATED
    assert events[0].payload.practice_id == "P1"


def test_router_without_event_log_only_writes_jsonl(tmp_path: Path):
    fh = io.StringIO()
    router = FindingsRouter(fh)
    msg, dup = router.receive(_args())
    assert dup is False
    assert fh.getvalue().count("\n") == 1


def test_router_dedup_skips_event_log(tmp_path: Path):
    fh = io.StringIO()
    event_log = EventLogWriter(tmp_path / "events.jsonl")
    router = FindingsRouter(fh, event_log=event_log)

    router.receive(_args())
    msg, dup = router.receive(_args())
    assert dup is True
    assert fh.getvalue().count("\n") == 1
    # Only one event emitted (duplicate suppressed)
    events = EventLogReader(tmp_path / "events.jsonl").read_all()
    assert len(events) == 1


def test_router_swallows_event_log_errors_to_preserve_jsonl_durability(tmp_path: Path):
    """A failing EventLogWriter must not break the router. JSONL must still be written."""

    class _FailingEventLog:
        def emit(self, event):
            raise RuntimeError("simulated event log failure")

    fh = io.StringIO()
    router = FindingsRouter(fh, event_log=_FailingEventLog())

    msg, dup = router.receive(_args())

    assert fh.getvalue().count("\n") == 1
    assert dup is False
    assert "Finding #1 recorded." in msg
