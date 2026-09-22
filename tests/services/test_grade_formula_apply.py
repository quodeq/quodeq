"""Tests for grade-formula pure compute / preview / apply.

Split from test_grade_formula.py.
"""
from __future__ import annotations

import dataclasses
import shutil
from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.projection.grade_projector import compute_run_grades, recompute_grades
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services import grade_formula

from tests.services._grade_formula_fixtures import formula_path  # noqa: F401 -- pytest fixture

_STRICT = dataclasses.replace(
    DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 6.0, "minor": 0.25},
)


def _make_run(tmp_path: Path) -> Path:
    """Create a run dir with findings and baked default grade tables."""
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "events.jsonl").write_text("")  # marker; findings inserted directly
    store = SQLiteStateStore(run_dir)
    for i in range(6):
        store.record_finding(Judgment(
            practice_id="p1", dimension="security", req=f"req{i}",
            verdict="violation", severity="major", file=f"f{i}.py", line=1,
            title=f"t{i}", reason=f"r{i}",
        ))
    for i in range(8):
        store.record_finding(Judgment(
            practice_id="p1", dimension="security", req=f"c{i}",
            verdict="compliance", severity="minor", file=f"g{i}.py", line=1,
            title=f"ct{i}", reason=f"cr{i}",
        ))
    recompute_grades(run_dir, params=DEFAULT_PARAMS)
    return run_dir


def test_compute_run_grades_is_pure(tmp_path):
    run_dir = _make_run(tmp_path)
    store = SQLiteStateStore(run_dir)
    before_rows = store.read_dimension_scores()

    principle_rows, dim_rows = compute_run_grades(run_dir, _STRICT)

    assert dim_rows  # something was computed
    assert store.read_dimension_scores() == before_rows  # nothing written


def test_preview_equals_apply(tmp_path):
    """THE invariant: preview numbers == numbers after writing with same params."""
    run_dir = _make_run(tmp_path)
    _, preview_dims = compute_run_grades(run_dir, _STRICT)
    recompute_grades(run_dir, params=_STRICT)
    applied = SQLiteStateStore(run_dir).read_dimension_scores()
    applied_by_dim = {r["dimension"]: (r["score"], r["grade"]) for r in applied}
    for d in preview_dims:
        assert applied_by_dim[d["dimension"]] == (d["score"], d["grade"])


def test_apply_to_all_runs_rescores_and_skips_legacy(tmp_path, formula_path):
    project_dir = tmp_path / "proj-uuid"
    project_dir.mkdir()
    run_dir = project_dir / "run1"
    shutil.move(str(_make_run(tmp_path)), str(run_dir))
    legacy = project_dir / "run0"
    legacy.mkdir()  # no events.jsonl → must be skipped

    grade_formula.save_params(_STRICT)
    result = grade_formula.apply_to_all_runs(tmp_path)
    assert result.rescored == 1
    assert result.failed == []


def test_apply_to_all_runs_reports_failed_runs_and_continues(tmp_path, formula_path, monkeypatch):
    # A run whose recompute keeps failing (e.g. a genuinely corrupt db) must
    # be REPORTED in .failed rather than silently skipped — otherwise it keeps
    # serving old-formula grades while its siblings show the new formula, with
    # the apply falsely reporting full success. Other runs still rescore and
    # the cache is still cleared.
    project = tmp_path / "proj"
    for name in ("run-good", "run-bad"):
        d = project / name
        d.mkdir(parents=True)
        (d / "events.jsonl").write_text("")

    seen = []

    def flaky(run_dir, params=None):
        seen.append(run_dir.name)
        if run_dir.name == "run-bad":
            raise RuntimeError("database is locked")

    monkeypatch.setattr(
        "quodeq.data.projection.grade_projector.recompute_grades", flaky,
    )
    cleared = {"n": 0}
    monkeypatch.setattr(
        "quodeq.services.dashboard.clear_shared_dimension_cache",
        lambda: cleared.__setitem__("n", cleared["n"] + 1),
    )

    result = grade_formula.apply_to_all_runs(tmp_path)
    assert result.rescored == 1
    assert result.failed == ["run-bad"]
    assert "run-good" in seen
    assert cleared["n"] == 1  # cache cleared despite the partial failure


def test_apply_to_all_runs_clears_cache_when_root_missing(formula_path, monkeypatch, tmp_path):
    """Cache is cleared even when reports_root doesn't exist (returns 0)."""
    cleared = {"called": False}
    import quodeq.services.dashboard as dashboard

    def fake_clear():
        cleared["called"] = True
    monkeypatch.setattr(dashboard, "clear_shared_dimension_cache", fake_clear)

    result = grade_formula.apply_to_all_runs(tmp_path / "does-not-exist")
    assert result.rescored == 0
    assert result.failed == []
    assert cleared["called"] is True


def test_preview_scores_reads_only_and_reports_before_after(tmp_path, formula_path):
    project_dir = tmp_path / "proj-uuid"
    project_dir.mkdir()
    run_dir = project_dir / "run1"
    shutil.move(str(_make_run(tmp_path)), str(run_dir))

    db_before = (run_dir / "evaluation.db").read_bytes()
    result = grade_formula.preview_scores(tmp_path, "proj-uuid", _STRICT)
    assert result is not None
    assert result["runId"] == "run1"
    assert result["before"]["overall"]["score"] is not None
    assert result["after"]["overall"]["score"] is not None
    assert result["after"]["overall"]["score"] != result["before"]["overall"]["score"]
    assert (run_dir / "evaluation.db").read_bytes() == db_before  # read-only


def test_preview_scores_none_when_no_runs(tmp_path, formula_path):
    (tmp_path / "empty-proj").mkdir()
    assert grade_formula.preview_scores(tmp_path, "empty-proj", DEFAULT_PARAMS) is None
    assert grade_formula.preview_scores(tmp_path, "missing", DEFAULT_PARAMS) is None
