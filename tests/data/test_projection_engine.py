from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _write_events(log: Path, n: int) -> None:
    writer = EventLogWriter(log)
    for i in range(n):
        payload = JudgmentPayload(
            practice_id=f"P{i}", verdict="violation", dimension="Security",
            file=f"f{i}.py", line=i + 1, reason="r",
        )
        writer.emit(JudgmentCreatedEvent(payload=payload))


def _write_events_append(log: Path, *, start_i: int, n: int) -> None:
    writer = EventLogWriter(log)
    for i in range(start_i, start_i + n):
        payload = JudgmentPayload(
            practice_id=f"P{i}", verdict="violation", dimension="Security",
            file=f"f{i}.py", line=i + 1, reason="r",
        )
        writer.emit(JudgmentCreatedEvent(payload=payload))


def test_rebuild_projects_all_events(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    engine = ProjectionEngine()
    count = engine.rebuild(log, tmp_path)
    assert count == 3
    with open_evaluation_db(tmp_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert n == 3


def test_rebuild_is_idempotent(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    engine = ProjectionEngine()
    engine.rebuild(log, tmp_path)
    engine.rebuild(log, tmp_path)
    with open_evaluation_db(tmp_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert n == 2


def test_rebuild_saves_checkpoint(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    _write_events(log, 1)
    engine = ProjectionEngine()
    engine.rebuild(log, tmp_path)
    store = SQLiteStateStore(tmp_path)
    assert store.get_checkpoint() is not None


def test_rebuild_skips_corrupt_events(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    writer = EventLogWriter(log)
    p1 = JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="f.py", line=1, reason="r",
    )
    writer.emit(JudgmentCreatedEvent(payload=p1))
    with open(log, "a") as f:
        f.write("NOT_VALID_JSON\n")
    p2 = JudgmentPayload(
        practice_id="P2", verdict="violation", dimension="Security",
        file="g.py", line=2, reason="r",
    )
    writer.emit(JudgmentCreatedEvent(payload=p2))
    engine = ProjectionEngine()
    count = engine.rebuild(log, tmp_path)
    assert count == 2
    with open_evaluation_db(tmp_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert n == 2


def test_update_processes_only_new_events(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    writer = EventLogWriter(log)
    engine = ProjectionEngine()

    p1 = JudgmentPayload(
        practice_id="P1", verdict="violation", dimension="Security",
        file="f1.py", line=1, reason="r",
    )
    writer.emit(JudgmentCreatedEvent(payload=p1))
    engine.update(log, tmp_path)

    time.sleep(0.01)

    p2 = JudgmentPayload(
        practice_id="P2", verdict="violation", dimension="Security",
        file="f2.py", line=2, reason="r",
    )
    writer.emit(JudgmentCreatedEvent(payload=p2))
    count = engine.update(log, tmp_path)

    assert count == 1
    with open_evaluation_db(tmp_path) as conn:
        n = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert n == 2


def test_update_with_no_new_events_returns_zero(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    _write_events(log, 1)
    engine = ProjectionEngine()
    engine.update(log, tmp_path)
    count = engine.update(log, tmp_path)
    assert count == 0


def test_update_without_prior_checkpoint_processes_all(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    _write_events(log, 3)
    engine = ProjectionEngine()
    count = engine.update(log, tmp_path)
    assert count == 3


def test_project_holds_one_connection_for_the_whole_replay(tmp_path: Path):
    """rebuild() opens O(1) connections, not O(events).

    clear_all() and the event replay each hold their own connection (2
    total, independent of event count) via store.clear_all() and
    store.connection() respectively - clear_all() already reuses a held
    connection when one is open, so this stays O(1) rather than O(events).
    """
    log = tmp_path / "events.jsonl"
    _write_events(log, 5)
    engine = ProjectionEngine()

    from quodeq.data.sqlite import state_store as state_store_mod

    calls = {"n": 0}
    real_factory = state_store_mod.open_evaluation_db

    def counting_factory(*a, **kw):
        calls["n"] += 1
        return real_factory(*a, **kw)

    with patch.object(state_store_mod, "open_evaluation_db", counting_factory):
        engine.rebuild(log, tmp_path)

    assert calls["n"] == 2, "expected one connection for clear_all and one for the event replay"


def test_update_resumes_from_stored_byte_offset_not_a_full_reparse(tmp_path: Path):
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    engine = ProjectionEngine()
    engine.rebuild(log, tmp_path)

    # Append 1 more event.
    _write_events_append(log, start_i=2, n=1)

    from quodeq.data.events.reader import EventLogReader
    real_stream = EventLogReader.stream
    seen_offsets = []

    def spying_stream(self, since_timestamp=None, from_offset=0):
        seen_offsets.append(from_offset)
        return real_stream(self, since_timestamp=since_timestamp, from_offset=from_offset)

    with patch.object(EventLogReader, "stream", spying_stream):
        count = engine.update(log, tmp_path)

    assert count == 1
    assert seen_offsets and seen_offsets[-1] > 0, "update() must seek past already-projected bytes"


def test_update_captures_size_before_read_loop_not_after(tmp_path: Path):
    """Regression for the byte-offset resume bug: a writer appending between
    "reader reached EOF" and the post-loop ``stat()`` call must not have its
    bytes folded into the saved projected size.

    ``_project`` must capture ``event_log.stat().st_size`` BEFORE the read
    loop starts, not after it. Capturing it after means a concurrently
    appended event's bytes get counted as already-projected even though they
    were never read, and the next ``update()`` seeks past them: the event is
    silently and permanently dropped.
    """
    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    engine = ProjectionEngine()
    engine.rebuild(log, tmp_path)

    # Append event #3 - this is the one the update() call below should project.
    _write_events_append(log, start_i=2, n=1)

    from quodeq.data.events.reader import EventLogReader
    real_stream = EventLogReader.stream
    appended = {"done": False}

    def racing_stream(self, since_timestamp=None, from_offset=0):
        events = list(real_stream(self, since_timestamp=since_timestamp, from_offset=from_offset))
        for i, event in enumerate(events):
            yield event
            if i == len(events) - 1 and not appended["done"]:
                # Simulate a writer appending event #4 right after the reader
                # reaches EOF but before ``_project`` would re-stat the file.
                appended["done"] = True
                _write_events_append(log, start_i=3, n=1)

    with patch.object(EventLogReader, "stream", racing_stream):
        count = engine.update(log, tmp_path)

    assert count == 1  # only event #3; the racily-appended event #4 wasn't read this call

    # Event #4's bytes must NOT be marked as already-projected: the next
    # update() call must still find and project it.
    count2 = engine.update(log, tmp_path)
    assert count2 == 1, "event appended mid-read was permanently dropped by the offset bug"


def test_reader_from_offset_skips_already_consumed_lines(tmp_path: Path):
    from quodeq.data.events.reader import EventLogReader

    log = tmp_path / "events.jsonl"
    _write_events(log, 2)
    offset_after_first_pass = log.stat().st_size
    _write_events_append(log, start_i=2, n=1)

    events = list(EventLogReader(log).stream(from_offset=offset_after_first_pass))
    assert len(events) == 1
    assert events[0].payload.file == "f2.py"
