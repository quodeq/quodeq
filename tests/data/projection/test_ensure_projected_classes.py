"""Projector.ensure_projected re-derives the grade tables when the severity classes change.

The classes are part of the grade math: a project override (or a standard
edit) changes the numbers without touching the event or action logs, so the
grade tables stamp a fingerprint of the classes they were computed with and
a mismatch reads as stale, like an older GRADE_ALGO_VERSION.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.data.projection.projector import ProjectionResult, Projector
from quodeq.data.sqlite.state_store import SQLiteStateStore
from tests.data.projection._ensure_projected_helpers import _seed_run_with_finding


def _project_with_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    (repo / ".quodeq").mkdir(parents=True)
    project_dir = tmp_path / "reports" / "proj"
    run_dir = project_dir / "r1"
    run_dir.mkdir(parents=True)
    (project_dir / "repository_info.json").write_text(json.dumps({"path": str(repo)}), encoding="utf-8")
    return repo, project_dir, run_dir


def _principle_score(run_dir: Path) -> float:
    (grade,) = SQLiteStateStore(run_dir).read_principle_grades()
    return grade["score"]


def test_an_override_severity_change_re_derives_the_grades(tmp_path: Path) -> None:
    repo, project_dir, run_dir = _project_with_repo(tmp_path)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    before = _principle_score(run_dir)

    with patch("quodeq.data.projection.grade_projector.recompute_grades") as spy:
        result = Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
        assert result == ProjectionResult(events_projected=0, rebuilt=False)
        assert spy.call_count == 0

    overrides = repo / ".quodeq" / "standards-overrides.json"
    overrides.write_text(json.dumps({"version": 1, "overrides": {"R1": {"severity": "critical"}}}), encoding="utf-8")
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    as_critical = _principle_score(run_dir)
    assert as_critical < before

    overrides.write_text(json.dumps({"version": 1, "overrides": {"R1": {"severity": "major"}}}), encoding="utf-8")
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    assert as_critical < _principle_score(run_dir) < before


def test_a_table_without_the_fingerprint_heals_on_first_contact(tmp_path: Path) -> None:
    from quodeq.data.sqlite.connection import open_evaluation_db

    _repo, project_dir, run_dir = _project_with_repo(tmp_path)
    events_log = _seed_run_with_finding(run_dir, req="R1", file="a.py", line=10)
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    store = SQLiteStateStore(run_dir)
    stamped = store.get_grades_classes_fingerprint()
    assert stamped
    with open_evaluation_db(run_dir) as conn:
        conn.execute("DELETE FROM run_meta WHERE key = 'grades_severity_classes'")
        conn.commit()

    with patch("quodeq.data.projection.grade_projector.recompute_grades") as spy:
        Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
        assert spy.call_count == 1
    Projector().ensure_projected(events_log, run_dir, project_dir=project_dir)
    assert store.get_grades_classes_fingerprint() == stamped
