from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from quodeq.core.events.models import Judgment, JudgmentPayload
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


def test_projected_size_is_none_when_not_set(tmp_path: Path):
    assert SQLiteStateStore(tmp_path).get_projected_size() is None


def test_projected_size_round_trip(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    store.save_projected_size(1234)
    assert store.get_projected_size() == 1234


def test_clear_all_resets_projected_size(tmp_path: Path):
    store = SQLiteStateStore(tmp_path)
    store.save_projected_size(99)
    store.clear_all()
    assert store.get_projected_size() is None


def test_update_verdict_dismisses_existing_finding(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1",
    ))

    rows = store.update_verdict(req="R1", file="a.py", line=10, verdict="dismissed")

    assert rows == 1
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings WHERE requirement=? AND file=? AND line=?",
            ("R1", "a.py", 10),
        ).fetchone()
        assert row[0] == "dismissed"


def test_update_verdict_returns_zero_when_no_match(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    rows = store.update_verdict(req="R1", file="a.py", line=10, verdict="dismissed")
    assert rows == 0


def test_update_verdict_empty_req_returns_zero_when_no_match(tmp_path: Path) -> None:
    """The empty-req branch must report no match cleanly when there is no
    null/empty-requirement finding at that location."""
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="R1",  # has a req, NULL branch won't hit it
    ))

    rows = store.update_verdict(req="", file="a.py", line=10, verdict="dismissed")

    assert rows == 0


def test_update_verdict_empty_req_matches_empty_string_requirement(tmp_path: Path) -> None:
    """A finding physically stored with requirement='' (not NULL) is also
    matched by the empty-req branch."""
    store = SQLiteStateStore(tmp_path)
    store.record_finding(Judgment(
        practice_id="P1", verdict="violation", dimension="Security",
        file="a.py", line=10, reason="r", req="",  # stored as empty string
    ))

    rows = store.update_verdict(req="", file="a.py", line=10, verdict="dismissed")

    assert rows == 1
    with open_evaluation_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT verdict FROM findings WHERE file=? AND line=?", ("a.py", 10),
        ).fetchone()
        assert row[0] == "dismissed"


def test_actions_projected_size_round_trips(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    assert store.get_actions_projected_size() is None

    store.save_actions_projected_size(1234)
    assert store.get_actions_projected_size() == 1234

    store.save_actions_projected_size(5678)
    assert store.get_actions_projected_size() == 5678


def test_clear_all_resets_actions_projected_size(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.save_actions_projected_size(1234)
    store.clear_all()
    assert store.get_actions_projected_size() is None


def test_record_dimension_score_round_trip(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_dimension_score(dimension="Security", score=7.4, grade="B")

    rows = store.read_dimension_scores()
    assert rows == [{"dimension": "Security", "score": 7.4, "grade": "B"}]


def test_record_dimension_score_upserts(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_dimension_score(dimension="Security", score=7.4, grade="B")
    store.record_dimension_score(dimension="Security", score=8.2, grade="B+")

    rows = store.read_dimension_scores()
    assert rows == [{"dimension": "Security", "score": 8.2, "grade": "B+"}]


def test_record_principle_grade_round_trip(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_principle_grade(
        dimension="Security", principle_id="P1",
        score=6.0, grade="C", finding_count=3, dismissed_count=1,
    )

    rows = store.read_principle_grades()
    assert len(rows) == 1
    assert rows[0]["dimension"] == "Security"
    assert rows[0]["principle_id"] == "P1"
    assert rows[0]["score"] == 6.0
    assert rows[0]["grade"] == "C"
    assert rows[0]["finding_count"] == 3
    assert rows[0]["dismissed_count"] == 1


def test_clear_grades_truncates_both_tables(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_dimension_score(dimension="S", score=1.0, grade="F")
    store.record_principle_grade(
        dimension="S", principle_id="P", score=1.0, grade="F",
        finding_count=1, dismissed_count=0,
    )

    store.clear_grades()

    assert store.read_dimension_scores() == []
    assert store.read_principle_grades() == []


def test_read_run_score_from_dim_scores_averages(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    store.record_dimension_score(dimension="Security", score=7.0, grade="B-")
    store.record_dimension_score(dimension="Reliability", score=9.0, grade="A")

    run = store.read_run_score_from_dim_scores()
    assert run["score"] == 8.0
    assert run["grade"] is not None


def test_read_run_score_returns_none_when_empty(tmp_path: Path) -> None:
    store = SQLiteStateStore(tmp_path)
    assert store.read_run_score_from_dim_scores() == {"score": None, "grade": None}


def test_read_run_score_skips_null_dimension_scores(tmp_path: Path) -> None:
    """A dimension can have score=None (Insufficient evidence) — exclude from the average."""
    store = SQLiteStateStore(tmp_path)
    store.record_dimension_score(dimension="Security", score=8.0, grade="A-")
    store.record_dimension_score(dimension="Reliability", score=None, grade="Insufficient")

    run = store.read_run_score_from_dim_scores()
    assert run["score"] == 8.0  # only Security counts
