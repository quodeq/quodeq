"""Projection places every finding event in its standard.

The event log holds what was reported. Projection re-admits each finding
with the installed standards, so ``findings`` always names a real principle,
and one the standard cannot place is kept in ``unmapped_findings`` instead
of being graded under a blank principle.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.data.events.writer import EventLogWriter
from quodeq.data.projection import admission
from quodeq.data.projection.grade_projector import load_grade_inputs
from quodeq.data.projection.projector import Projector

pytestmark = pytest.mark.real_standards

DIM = "accessibility"


def _standard(directory: Path, principle: str = "Perceivable") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{DIM}.json").write_text(json.dumps({"id": DIM, "principles": [
        {"name": principle, "requirements": [{"id": "ACC-PER-01"}, {"id": "ACC-PER-02"}]},
        {"name": "Operable", "requirements": [{"id": "ACC-OPR-01"}]},
    ]}), encoding="utf-8")
    return directory


@pytest.fixture()
def standards(tmp_path: Path, monkeypatch) -> dict[str, Path]:
    dirs = {"compiled": _standard(tmp_path / "compiled"), "evaluators": tmp_path / "evaluators"}
    dirs["evaluators"].mkdir()
    monkeypatch.setattr(admission, "default_standards_dirs",
                        lambda: (dirs["compiled"], dirs["evaluators"]))
    return dirs


def _project(tmp_path: Path, findings: list[dict]) -> Path:
    run_dir = tmp_path / "project" / "run"
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    writer = EventLogWriter(log)
    for i, f in enumerate(findings):
        writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(
            verdict="violation", dimension=DIM, file=f"f{i}.kt", line=i + 1,
            reason="r", severity="major", **f,
        )))
    Projector().ensure_projected(log, run_dir, project_dir=run_dir.parent)
    return run_dir


def _rows(run_dir: Path, sql: str) -> list[tuple]:
    with sqlite3.connect(run_dir / "evaluation.db") as conn:
        return conn.execute(sql).fetchall()


def test_a_finding_without_a_principle_is_placed_by_its_requirement(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "", "req": "ACC-PER-01"}, {"practice_id": "", "req": "ACC-OPR-01"}])

    assert _rows(run, "SELECT practice_id, requirement FROM findings ORDER BY line") == [
        ("Perceivable", "ACC-PER-01"), ("Operable", "ACC-OPR-01"),
    ]


def test_a_near_miss_code_is_stored_under_the_canonical_one(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "", "req": "acc-per-2"}])

    assert _rows(run, "SELECT practice_id, requirement FROM findings") == [("Perceivable", "ACC-PER-02")]


def test_a_stale_principle_is_replaced_by_the_standards(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "Renamed Long Ago", "req": "ACC-PER-01"}])

    assert _rows(run, "SELECT practice_id FROM findings") == [("Perceivable",)]


def test_an_unplaceable_finding_is_unmapped_and_not_graded(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "", "req": "ZZZ-NOPE-9"}, {"practice_id": "", "req": "ACC-PER-01"}])

    assert _rows(run, "SELECT requirement, unmapped_reason FROM unmapped_findings") == [
        ("ZZZ-NOPE-9", "unknown_requirement"),
    ]
    inputs = load_grade_inputs(run)
    assert set(inputs.violations_by) == {(DIM, "Perceivable")}


def test_a_custom_standard_wins_over_the_built_in(tmp_path, standards) -> None:
    _standard(standards["evaluators"], principle="Custom Principle")

    run = _project(tmp_path, [{"practice_id": "", "req": "ACC-PER-01"}])

    assert _rows(run, "SELECT practice_id FROM findings") == [("Custom Principle",)]


def test_the_dimension_matches_its_standard_in_any_case(tmp_path, standards) -> None:
    run_dir = tmp_path / "project" / "run"
    run_dir.mkdir(parents=True)
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="", verdict="violation", dimension="Accessibility", file="a.kt", line=1,
        reason="r", severity="major", req="ACC-OPR-01",
    )))
    Projector().ensure_projected(log, run_dir, project_dir=run_dir.parent)

    assert _rows(run_dir, "SELECT practice_id, dimension FROM findings") == [("Operable", DIM)]


def test_without_a_standard_a_blank_principle_is_unmapped_never_stored(tmp_path, monkeypatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(admission, "default_standards_dirs", lambda: (empty, None))

    run = _project(tmp_path, [{"practice_id": "", "req": "ACC-PER-01"}, {"practice_id": "Named", "req": "X-1"}])

    assert _rows(run, "SELECT practice_id FROM findings") == [("Named",)]
    assert _rows(run, "SELECT unmapped_reason FROM unmapped_findings") == [("no_standard",)]


def _meta(run_dir: Path, key: str):
    rows = _rows(run_dir, f"SELECT value FROM run_meta WHERE key = '{key}'")
    return rows[0][0] if rows else None


def _reread(run_dir: Path):
    return Projector().ensure_projected(run_dir / "events.jsonl", run_dir, project_dir=run_dir.parent)


def test_a_run_projected_before_stamps_heals_on_first_read(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "", "req": "ACC-PER-01"}])
    with sqlite3.connect(run / "evaluation.db") as conn:  # a v9 DB an older quodeq left
        conn.executescript("""
            DROP TRIGGER findings_require_principle;
            DROP TRIGGER findings_keep_principle;
            DROP TABLE unmapped_findings;
            UPDATE findings SET practice_id = '';
            DELETE FROM run_meta WHERE key = 'standard_mapping_stamps';
            PRAGMA user_version = 9;
        """)

    result = _reread(run)

    assert result.rebuilt
    assert _rows(run, "SELECT practice_id FROM findings") == [("Perceivable",)]
    assert _rows(run, "SELECT count(*) FROM unmapped_findings") == [(0,)]
    assert _meta(run, "standard_mapping_stamps") is not None


def test_a_changed_mapping_re_places_the_findings(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "", "req": "ACC-PER-01"}])
    _standard(standards["compiled"], principle="Moved Here")

    assert _reread(run).rebuilt
    assert _rows(run, "SELECT practice_id FROM findings") == [("Moved Here",)]


def test_rewording_a_requirement_does_not_re_project(tmp_path, standards) -> None:
    run = _project(tmp_path, [{"practice_id": "", "req": "ACC-PER-01"}])
    path = standards["compiled"] / f"{DIM}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["principles"][0]["requirements"][0]["text"] = "Reworded."
    path.write_text(json.dumps(data), encoding="utf-8")

    result = _reread(run)

    assert result.events_projected == 0 and not result.rebuilt


def test_a_code_of_another_dimension_is_never_rerouted_by_projection(tmp_path, standards) -> None:
    """The per-dimension CLI report quarantines it, so the dashboard must too."""
    (standards["compiled"] / "security.json").write_text(json.dumps({"id": "security", "principles": [
        {"name": "Confidentiality", "requirements": [{"id": "S-CON-1"}]},
    ]}), encoding="utf-8")
    run_dir = tmp_path / "project" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(json.dumps({"state": "done", "dimensions": [DIM, "security"]}), encoding="utf-8")
    log = run_dir / "events.jsonl"
    EventLogWriter(log).emit(JudgmentCreatedEvent(payload=JudgmentPayload(
        practice_id="", verdict="violation", dimension=DIM, file="a.kt", line=1,
        reason="r", severity="major", req="S-CON-1",
    )))

    Projector().ensure_projected(log, run_dir, project_dir=run_dir.parent)

    assert _rows(run_dir, "SELECT count(*) FROM findings") == [(0,)]
    assert _rows(run_dir, "SELECT requirement, unmapped_reason FROM unmapped_findings") == [
        ("S-CON-1", "unknown_requirement"),
    ]
