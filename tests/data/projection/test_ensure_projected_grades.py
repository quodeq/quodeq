"""Projector.ensure_projected: grade tables, pre-PR-1 rebuild and grade-algo version reconciliation."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import FindingDismissed, FindingDismissedEvent
from quodeq.data.actions_log import ActionLogWriter
from quodeq.data.projection.projector import ProjectionResult, Projector
from quodeq.data.sqlite.connection import open_evaluation_db
from tests.data.projection._ensure_projected_helpers import _seed_run_with_finding, _verdict_for


def test_ensure_projected_populates_grade_tables(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    from quodeq.data.sqlite.state_store import SQLiteStateStore
    store = SQLiteStateStore(run_dir)
    assert len(store.read_dimension_scores()) == 1
    assert len(store.read_principle_grades()) == 1


def test_ensure_force_rebuilds_pre_pr1_db(tmp_path: Path) -> None:
    """Pre-PR-1 DBs were projected by older code that left ``findings.requirement``
    empty. They have a checkpoint but no ``projection_event_log_size`` key. On
    first contact, ensure_projected must force a rebuild so the new mappers
    populate every column (otherwise dismissals via UPDATE WHERE requirement=?
    match zero rows and silently no-op).
    """
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)

    # Project normally so the DB has rows.
    Projector().project(events_log, run_dir)
    # Simulate the pre-PR-1 state: requirement was never written, and the
    # projection_event_log_size key (added in PR 1) is absent.
    with open_evaluation_db(run_dir) as conn:
        conn.execute("UPDATE findings SET requirement = ''")
        conn.execute(
            "DELETE FROM run_meta WHERE key = 'projection_event_log_size'"
        )
        conn.commit()
    assert _verdict_for(run_dir, "R1", "a.py", 10) is None  # match-by-req fails

    # Dismiss the finding via the action log.
    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    )

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    # Force-rebuild rewrites requirement from events.jsonl, then the dismiss applies.
    assert _verdict_for(run_dir, "R1", "a.py", 10) == "dismissed"


def test_ensure_projected_grade_updates_after_dismiss(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    from quodeq.data.sqlite.state_store import SQLiteStateStore
    store = SQLiteStateStore(run_dir)
    # Sanity: grade exists initially.
    assert len(store.read_dimension_scores()) == 1

    ActionLogWriter(project_dir).emit(
        FindingDismissedEvent(payload=FindingDismissed(req="R1", file="a.py", line=10))
    )
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    # All findings dismissed → no dimension rows.
    assert store.read_dimension_scores() == []
    assert store.read_principle_grades() == []


# --- grade-algo version reconciliation ---------------------------------------
#
# The grade tables embody the scoring math that computed them. When that math
# changes (clamp-order fix and successors), a run with untouched logs must
# still get its grades re-derived once — otherwise the same principle reads
# one number from SQL-backed screens and another from a fresh rescore.


def test_stale_grade_algo_recomputes_once_then_no_ops(tmp_path: Path) -> None:
    from unittest.mock import patch

    from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION
    from quodeq.data.sqlite.state_store import SQLiteStateStore

    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    store = SQLiteStateStore(run_dir)
    assert store.get_grades_algo_version() == GRADE_ALGO_VERSION

    # Simulate a DB graded by older math: same tables, older (or absent) stamp.
    store.save_grades_algo_version(GRADE_ALGO_VERSION - 1)

    with patch("quodeq.data.projection.grade_projector.recompute_grades") as spy:
        Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
        assert spy.call_count == 1

    # The patched call above didn't restamp; run the real thing once.
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    assert store.get_grades_algo_version() == GRADE_ALGO_VERSION

    # Fresh logs + current stamp → full fast no-op, no recompute.
    with patch("quodeq.data.projection.grade_projector.recompute_grades") as spy:
        result = Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
        assert result == ProjectionResult(events_projected=0, rebuilt=False)
        assert spy.call_count == 0


def test_pre_stamp_db_heals_on_first_contact(tmp_path: Path) -> None:
    """A DB projected before the stamp existed (no run_meta key) re-derives grades."""
    from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION
    from quodeq.data.sqlite.connection import open_evaluation_db as _open
    from quodeq.data.sqlite.state_store import SQLiteStateStore

    project_dir = tmp_path / "project"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    store = SQLiteStateStore(run_dir)
    # Erase the stamp to reproduce a pre-stamp DB.
    with _open(run_dir) as conn:
        conn.execute("DELETE FROM run_meta WHERE key = 'grades_algo_version'")
        conn.commit()
    assert store.get_grades_algo_version() is None

    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)

    assert store.get_grades_algo_version() == GRADE_ALGO_VERSION
    assert len(store.read_dimension_scores()) == 1


def test_grade_algo_version_is_three() -> None:
    """v3: the tally groups findings by ``req`` before ``vt`` (issue #1274).

    Grade tables stamped v2 were computed with vt-grouped tallies, so a
    run untouched since then must re-derive; the staleness test above proves
    the mechanism, this pins the version that triggers it.
    """
    from quodeq.core.scoring.projector_scoring import GRADE_ALGO_VERSION

    assert GRADE_ALGO_VERSION == 3
