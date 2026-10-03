import json
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload, EventType, Judgment
from quodeq.data.events.writer import EventLogWriter
from quodeq.analysis.checks import runner


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "events.jsonl"


@pytest.fixture
def writer(log_path: Path) -> EventLogWriter:
    return EventLogWriter(log_path)


def test_emit_judgment_event(writer: EventLogWriter, log_path: Path):
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
    event = JudgmentCreatedEvent(payload=payload)
    writer.emit(event)

    assert log_path.exists()
    assert log_path.stat().st_size > 0

    with open(log_path, "r") as f:
        data = json.loads(f.readline())

    assert data["event_type"] == EventType.JUDGMENT_CREATED
    assert data["payload"]["practice_id"] == "clean-arch-001"
    assert data["payload"]["verdict"] == "violation"
    assert data["payload"]["line"] == 42
    assert "event_id" in data
    assert "timestamp" in data


def test_multiple_events_append(writer: EventLogWriter, log_path: Path):
    payload1 = JudgmentPayload(practice_id="p1", verdict="compliance", dimension="D1", file="f1", line=1, reason="r1")
    payload2 = JudgmentPayload(practice_id="p2", verdict="violation", dimension="D1", file="f2", line=2, reason="r2")

    writer.emit(JudgmentCreatedEvent(payload=payload1))
    writer.emit(JudgmentCreatedEvent(payload=payload2))

    with open(log_path, "r") as f:
        lines = f.readlines()

    assert len(lines) == 2
    assert "p1" in lines[0]
    assert "p2" in lines[1]


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


class _CountingLock:
    """Stands in for the platform file lock; records how often a write took it."""

    def __init__(self) -> None:
        self.acquired = 0

    def acquire(self, f) -> None:
        self.acquired += 1

    def release(self, f) -> None:
        pass


def _judgments(n: int) -> list[Judgment]:
    return [
        Judgment(practice_id="P1", verdict="violation", dimension="security",
                 file="a.py", line=i, reason="r")
        for i in range(1, n + 1)
    ]


def test_emit_many_appends_every_event_under_one_lock(tmp_path: Path, monkeypatch):
    lock = _CountingLock()
    monkeypatch.setattr("quodeq.data.events.writer.get_file_lock", lambda: lock)
    log = tmp_path / "events.jsonl"

    EventLogWriter(log).emit_many(JudgmentCreatedEvent(payload=j) for j in _judgments(5))

    lines = log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["payload"]["line"] for line in lines] == [1, 2, 3, 4, 5]
    assert lock.acquired == 1


def test_emit_many_with_no_events_creates_no_file(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    EventLogWriter(log).emit_many([])
    assert not log.exists()


def test_emit_many_serializes_first_so_a_bad_event_leaves_the_log_untouched(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    good = JudgmentCreatedEvent(payload=_judgments(1)[0])
    with pytest.raises(Exception):
        EventLogWriter(log).emit_many([good, object()])  # type: ignore[list-item]
    assert not log.exists()


def test_persist_mirrors_every_judgment_with_one_lock(tmp_path: Path, monkeypatch):
    lock = _CountingLock()
    monkeypatch.setattr("quodeq.data.events.writer.get_file_lock", lambda: lock)
    jsonl = tmp_path / "evidence" / "security.jsonl"
    jsonl.parent.mkdir()
    judgments = _judgments(4)
    rows = [{"p": "P1", "file": "a.py", "line": j.line} for j in judgments]

    runner._persist(jsonl, judgments, rows)

    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 4
    assert lock.acquired == 1


def test_persist_logs_and_keeps_the_jsonl_write_when_the_mirror_fails(
    tmp_path: Path, monkeypatch, caplog,
):
    """A TypeError mirroring judgments into events.jsonl (e.g. a bad
    payload json.dumps can't serialize) must be caught and logged: the
    findings are already in the per-dim JSONL, so this only costs the
    live-feed mirror."""
    class _BrokenWriter:
        def __init__(self, path: Path) -> None:
            pass

        def emit_many(self, events) -> None:
            raise TypeError("not serializable")

    monkeypatch.setattr("quodeq.data.events.writer.EventLogWriter", _BrokenWriter)
    jsonl = tmp_path / "evidence" / "security.jsonl"
    jsonl.parent.mkdir()
    judgments = _judgments(1)
    rows = [{"p": "P1", "file": "a.py", "line": 1}]

    with caplog.at_level("WARNING"):
        runner._persist(jsonl, judgments, rows)

    assert jsonl.read_text(encoding="utf-8").strip() != ""
    assert any("could not mirror findings to the event log" in r.message for r in caplog.records)


def test_persist_propagates_an_unnamed_mirror_error(tmp_path: Path, monkeypatch):
    """A mirror failure outside (OSError, TypeError, ValueError) must
    propagate, not be swallowed."""
    class _BrokenWriter:
        def __init__(self, path: Path) -> None:
            pass

        def emit_many(self, events) -> None:
            raise RuntimeError("unexpected")

    monkeypatch.setattr("quodeq.data.events.writer.EventLogWriter", _BrokenWriter)
    jsonl = tmp_path / "evidence" / "security.jsonl"
    jsonl.parent.mkdir()

    with pytest.raises(RuntimeError, match="unexpected"):
        runner._persist(jsonl, _judgments(1), [{"p": "P1", "file": "a.py", "line": 1}])
