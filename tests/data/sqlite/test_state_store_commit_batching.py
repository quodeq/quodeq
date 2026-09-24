"""A held SQLiteStateStore connection commits once, not once per finding."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection.engine import ProjectionEngine
from quodeq.data.sqlite import connection as connection_mod
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore

_FINDINGS = 50


class _CommitCounter:
    """Wraps a sqlite3 connection and counts commit() calls."""

    def __init__(self, conn, commits: list[int]) -> None:
        self._conn = conn
        self._commits = commits

    def commit(self) -> None:
        self._commits.append(1)
        self._conn.commit()

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def commits(monkeypatch) -> list[int]:
    seen: list[int] = []
    real_open = connection_mod.open_evaluation_db

    @contextmanager
    def counting_open(run_dir):
        with real_open(run_dir) as conn:
            yield _CommitCounter(conn, seen)

    monkeypatch.setattr("quodeq.data.sqlite.state_store.open_evaluation_db", counting_open)
    return seen


def _payload(line: int) -> JudgmentPayload:
    return JudgmentPayload(practice_id="P1", verdict="violation", dimension="security",
                           file="a.py", line=line, reason="r")


def _count_findings(run_dir: Path) -> int:
    with open_evaluation_db(run_dir) as conn:
        return conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]


def test_held_connection_commits_once_for_many_findings(tmp_path, commits):
    store = SQLiteStateStore(tmp_path)
    with store.connection():
        for line in range(1, _FINDINGS + 1):
            store.record_finding(_payload(line))
    assert len(commits) == 1
    assert _count_findings(tmp_path) == _FINDINGS


def test_record_finding_without_a_held_connection_still_commits(tmp_path, commits):
    SQLiteStateStore(tmp_path).record_finding(_payload(1))
    assert len(commits) == 1
    assert _count_findings(tmp_path) == 1


def test_a_failed_batch_commits_none_of_its_findings(tmp_path):
    store = SQLiteStateStore(tmp_path)
    with pytest.raises(RuntimeError):
        with store.connection():
            store.record_finding(_payload(1))
            raise RuntimeError("replay aborted")
    assert _count_findings(tmp_path) == 0


def _write_events(log: Path, lines: range) -> None:
    writer = EventLogWriter(log)
    for line in lines:
        writer.emit(JudgmentCreatedEvent(payload=_payload(line)))


def test_rebuild_replay_commits_a_bounded_number_of_times(tmp_path, commits):
    log = tmp_path / "events.jsonl"
    _write_events(log, range(1, _FINDINGS + 1))

    ProjectionEngine().rebuild(log, tmp_path)

    # clear_all, save_checkpoint, save_projected_size, and the exit commit.
    assert len(commits) <= 4
    assert _count_findings(tmp_path) == _FINDINGS


def test_a_replay_after_an_aborted_batch_lands_every_finding_once(tmp_path, monkeypatch):
    log = tmp_path / "events.jsonl"
    _write_events(log, range(1, 11))
    real_record = SQLiteStateStore.record_finding
    calls = {"n": 0}

    def flaky(self, payload):
        calls["n"] += 1
        if calls["n"] == 6:
            import sqlite3
            raise sqlite3.OperationalError("disk I/O error")
        real_record(self, payload)

    monkeypatch.setattr(SQLiteStateStore, "record_finding", flaky)
    with pytest.raises(Exception):
        ProjectionEngine().update(log, tmp_path)
    monkeypatch.setattr(SQLiteStateStore, "record_finding", real_record)

    ProjectionEngine().update(log, tmp_path)

    assert _count_findings(tmp_path) == 10
