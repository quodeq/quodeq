"""Test that batch_rewrite_grades is atomic (finding #257).

A mid-batch failure must leave pre-existing grade rows intact --
not clear them and leave the table empty/half-written.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.data.sqlite.connection import open_evaluation_db
from quodeq.data.sqlite.state_store import SQLiteStateStore


def _seed_existing_grades(run_dir: Path) -> None:
    """Write two principle_grades and one dimension_scores row as pre-existing data."""
    store = SQLiteStateStore(run_dir)
    store.record_principle_grade(
        dimension="Security",
        principle_id="P1",
        score=8.0,
        grade="Good",
        finding_count=1,
        dismissed_count=0,
    )
    store.record_principle_grade(
        dimension="Security",
        principle_id="P2",
        score=6.0,
        grade="Adequate",
        finding_count=2,
        dismissed_count=0,
    )
    store.record_dimension_score(dimension="Security", score=7.0, grade="Good")


def test_batch_rewrite_grades_method_exists(tmp_path: Path):
    """SQLiteStateStore must expose batch_rewrite_grades."""
    store = SQLiteStateStore(tmp_path)
    assert hasattr(store, "batch_rewrite_grades"), (
        "SQLiteStateStore is missing batch_rewrite_grades"
    )
    assert callable(store.batch_rewrite_grades)


def test_batch_rewrite_rolls_back_on_mid_insert_failure(tmp_path: Path):
    """batch_rewrite_grades must be fully atomic.

    Seed existing rows -> attempt a batch rewrite where one insert raises ->
    assert the pre-existing rows are still there (transaction was rolled back).
    """
    store = SQLiteStateStore(tmp_path)
    _seed_existing_grades(tmp_path)

    # Verify the seed is in place.
    before = store.read_principle_grades()
    assert len(before) == 2, "Seed should have 2 principle grades"

    # principle_rows: second entry has None principle_id to cause a SQL error mid-batch.
    principle_rows = [
        ("Security", {"principle_id": "NEW-P1", "score": 9.0, "grade": "Exemplary",
                      "finding_count": 0, "dismissed_count": 0}),
        ("Security", {"principle_id": None, "score": 5.0, "grade": "Adequate",
                      "finding_count": 1, "dismissed_count": 0}),  # will fail NOT NULL
    ]
    dimension_rows = [{"dimension": "Security", "score": 9.0, "grade": "Exemplary"}]

    with pytest.raises(Exception):
        store.batch_rewrite_grades(principle_rows, dimension_rows)

    # The pre-existing rows must be intact -- clear + inserts were rolled back.
    after = store.read_principle_grades()
    assert len(after) == 2, (
        f"Pre-existing rows must survive a failed batch rewrite, got {after}"
    )
    ids = {r["principle_id"] for r in after}
    assert ids == {"P1", "P2"}, f"Wrong IDs after rollback: {ids}"


def test_batch_rewrite_succeeds_replaces_all_grades(tmp_path: Path):
    """A successful batch_rewrite_grades replaces all old grades with new ones."""
    store = SQLiteStateStore(tmp_path)
    _seed_existing_grades(tmp_path)

    new_principle_rows = [
        ("Maintainability", {"principle_id": "M1", "score": 9.5, "grade": "Exemplary",
                             "finding_count": 0, "dismissed_count": 0}),
    ]
    new_dimension_rows = [{"dimension": "Maintainability", "score": 9.5, "grade": "Exemplary"}]

    store.batch_rewrite_grades(new_principle_rows, new_dimension_rows)

    principle_grades = store.read_principle_grades()
    assert len(principle_grades) == 1
    assert principle_grades[0]["principle_id"] == "M1"

    dim_scores = store.read_dimension_scores()
    assert len(dim_scores) == 1
    assert dim_scores[0]["dimension"] == "Maintainability"
