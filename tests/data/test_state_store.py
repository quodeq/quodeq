from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.events.models import JudgmentPayload
from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _payload(**kw) -> JudgmentPayload:
    defaults = dict(
        practice_id="P1", verdict="violation", dimension="Security",
        file="src/auth.py", line=42, reason="hardcoded secret",
    )
    return JudgmentPayload(**{**defaults, **kw})


def test_checkpoint_is_none_when_not_set(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    assert store.get_checkpoint() is None


def test_checkpoint_round_trip(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    ts = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    store.save_checkpoint(ts)
    assert store.get_checkpoint() == ts


def test_save_checkpoint_overwrites_previous(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    ts1 = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 5, 15, 11, 0, 0, tzinfo=timezone.utc)
    store.save_checkpoint(ts1)
    store.save_checkpoint(ts2)
    assert store.get_checkpoint() == ts2


def test_record_finding_inserts_finding(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    store.record_finding(_payload())
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute("SELECT practice_id, verdict FROM findings").fetchone()
    assert row[0] == "P1"
    assert row[1] == "violation"


def test_record_finding_is_idempotent(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    store.record_finding(_payload())
    store.record_finding(_payload())  # same dedup_key
    with open_evaluation_db(tmp_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
    assert count == 1


def test_clear_all_empties_findings_and_scores(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    store.record_finding(_payload())
    with open_evaluation_db(tmp_path) as conn:
        conn.execute(
            "INSERT INTO dimension_scores (dimension, score, grade, confidence) "
            "VALUES ('Security', 80.0, 'B', 'high')"
        )
        conn.commit()
    store.clear_all()
    with open_evaluation_db(tmp_path) as conn:
        findings = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        scores = conn.execute("SELECT COUNT(*) FROM dimension_scores").fetchone()[0]
    assert findings == 0
    assert scores == 0


def test_clear_all_preserves_unrelated_run_meta(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    with open_evaluation_db(tmp_path) as conn:
        conn.execute("INSERT INTO run_meta VALUES ('job_id', 'abc-123')")
        conn.commit()
    store.clear_all()
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT value FROM run_meta WHERE key = 'job_id'"
        ).fetchone()
    assert row[0] == "abc-123"


def test_clear_all_resets_checkpoint(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    store.save_checkpoint(datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc))
    store.clear_all()
    assert store.get_checkpoint() is None
