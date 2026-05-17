"""Tests for the deleted (permanent suppression) findings storage service."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.data.projection.projector import Projector
from quodeq.services.deleted import (
    delete_all_dismissed,
    delete_finding,
    deleted_keys,
    is_finding_deleted,
    load_deleted,
)
from quodeq.services.dismissed import dismiss_finding, load_dismissed


def _finding(*, req="M-MOD-1", file="foo.py", line=10, dimension="maintainability", principle="Modularity"):
    return {
        "req": req, "file": file, "line": line,
        "dimension": dimension, "principle": principle, "severity": "minor",
    }


def _seed_projected_run(
    project_dir: Path,
    run_id: str,
    *,
    req: str,
    file: str,
    line: int,
    dimension: str = "maintainability",
    principle: str = "Modularity",
) -> Path:
    """Create a run with one violation finding projected into evaluation.db."""
    run_dir = project_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id=principle,
        verdict="violation",
        dimension=dimension,
        file=file,
        line=line,
        reason="r",
        req=req,
    )))
    Projector().project(log, run_dir)
    return run_dir


def _apply_actions(project_dir: Path, run_dir: Path) -> None:
    """Re-project actions log into the given run dir."""
    Projector().ensure_projected(
        run_dir / "events.jsonl", run_dir, project_dir=project_dir,
    )


class TestDeletedStorage:
    def test_load_empty_when_no_file(self, tmp_path):
        assert load_deleted(tmp_path / "nonexistent") == []

    def test_delete_creates_file_with_suppression_key(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        delete_finding(project_dir, _finding())
        entries = load_deleted(project_dir)
        assert len(entries) == 1
        assert entries[0]["dimension"] == "maintainability"
        assert entries[0]["principle"] == "Modularity"
        assert entries[0]["file"] == "foo.py"
        assert "deleted_at" in entries[0]

    def test_delete_deduplicates_same_key(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        delete_finding(project_dir, _finding(line=10))
        delete_finding(project_dir, _finding(line=99))  # different line, same (dim, principle, file)
        assert len(load_deleted(project_dir)) == 1

    def test_delete_requires_principle_and_file(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        delete_finding(project_dir, {"dimension": "x", "principle": "", "file": "f.py"})
        delete_finding(project_dir, {"dimension": "x", "principle": "P", "file": ""})
        assert load_deleted(project_dir) == []

    def test_deleted_keys_returns_tuple_set(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        delete_finding(project_dir, _finding())
        assert deleted_keys(project_dir) == {("maintainability", "Modularity", "foo.py")}

    def test_delete_sweeps_matching_dismissed_entries(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # Two dismissed entries share (dim, principle, file); a third does not.
        r1 = _seed_projected_run(project_dir, "r1", req="M-MOD-1", file="foo.py", line=10)
        r2 = _seed_projected_run(project_dir, "r2", req="M-MOD-1", file="foo.py", line=42)
        r3 = _seed_projected_run(project_dir, "r3", req="M-MOD-1", file="other.py", line=1)
        dismiss_finding(project_dir, _finding(line=10))
        dismiss_finding(project_dir, _finding(line=42))
        dismiss_finding(project_dir, _finding(file="other.py", line=1))
        _apply_actions(project_dir, r1)
        _apply_actions(project_dir, r2)
        _apply_actions(project_dir, r3)
        swept = delete_finding(project_dir, _finding(line=10))
        assert swept == 2

    def test_delete_returns_zero_swept_when_no_dismissed(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        assert delete_finding(project_dir, _finding()) == 0


class TestDeleteAllDismissed:
    def test_returns_zero_when_no_dismissed(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        assert delete_all_dismissed(project_dir) == 0

    def test_converts_dismissed_to_deleted_and_clears(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        r1 = _seed_projected_run(
            project_dir, "r1", req="A", file="a.py", line=1,
            dimension="maintainability", principle="Modularity",
        )
        r2 = _seed_projected_run(
            project_dir, "r2", req="B", file="b.py", line=2,
            dimension="maintainability", principle="Cohesion",
        )
        dismiss_finding(project_dir, _finding(req="A", file="a.py", line=1))
        dismiss_finding(project_dir, _finding(req="B", file="b.py", line=2, principle="Cohesion"))
        _apply_actions(project_dir, r1)
        _apply_actions(project_dir, r2)
        count = delete_all_dismissed(project_dir)
        assert count == 2
        keys = deleted_keys(project_dir)
        assert keys == {
            ("maintainability", "Modularity", "a.py"),
            ("maintainability", "Cohesion", "b.py"),
        }

    def test_collapses_duplicate_keys_in_dismissed_list(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        # Same (dim, principle, file) at two different lines.
        r1 = _seed_projected_run(project_dir, "r1", req="A", file="foo.py", line=1)
        r2 = _seed_projected_run(project_dir, "r2", req="B", file="foo.py", line=2)
        dismiss_finding(project_dir, _finding(req="A", line=1))
        dismiss_finding(project_dir, _finding(req="B", line=2))
        _apply_actions(project_dir, r1)
        _apply_actions(project_dir, r2)
        delete_all_dismissed(project_dir)
        assert len(load_deleted(project_dir)) == 1


class TestIsFindingDeleted:
    def test_empty_set_returns_false(self):
        assert is_finding_deleted(set(), dimension="x", principle="y", file="z") is False

    def test_match(self):
        s = {("security", "Path", "f.py")}
        assert is_finding_deleted(s, dimension="security", principle="Path", file="f.py") is True

    def test_no_match_on_different_file(self):
        s = {("security", "Path", "f.py")}
        assert is_finding_deleted(s, dimension="security", principle="Path", file="g.py") is False


class TestPersistedJson:
    def test_file_is_valid_json_list(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        delete_finding(project_dir, _finding())
        path = project_dir / "deleted.json"
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert data[0]["principle"] == "Modularity"
