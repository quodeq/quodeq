"""Tests for grade-formula params persistence."""
from __future__ import annotations

import dataclasses

import pytest

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services import grade_formula


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setattr(grade_formula, "grade_formula_path", lambda: path)
    return path


def test_load_returns_defaults_when_file_absent(formula_path):
    assert grade_formula.load_params() == DEFAULT_PARAMS
    assert grade_formula.is_custom() is False


def test_save_then_load_round_trips(formula_path):
    custom = dataclasses.replace(DEFAULT_PARAMS, base_k=0.3)
    grade_formula.save_params(custom)
    assert formula_path.is_file()
    assert grade_formula.load_params() == custom
    assert grade_formula.is_custom() is True


def test_load_falls_back_to_defaults_on_corrupt_file(formula_path):
    formula_path.write_text("{not json")
    assert grade_formula.load_params() == DEFAULT_PARAMS


def test_reset_removes_file(formula_path):
    grade_formula.save_params(dataclasses.replace(DEFAULT_PARAMS, base_k=0.3))
    grade_formula.reset_params()
    assert not formula_path.exists()
    assert grade_formula.is_custom() is False


def test_save_rejects_invalid_params(formula_path):
    bad = dataclasses.replace(DEFAULT_PARAMS, base_k=99.0)
    with pytest.raises(ValueError):
        grade_formula.save_params(bad)
    assert not formula_path.exists()


@pytest.mark.parametrize("payload", [
    "[1, 2, 3]",
    "null",
    '{"severityWeight": "oops"}',
    '{"severityWeight": [1, 2]}',
])
def test_load_falls_back_on_wrong_shape_json(formula_path, payload):
    formula_path.write_text(payload)
    assert grade_formula.load_params() == DEFAULT_PARAMS


def test_rescore_dimensions_uses_saved_params(formula_path, monkeypatch):
    """rescore_dimensions with no explicit params picks up the saved file."""
    import dataclasses
    from quodeq.services.rescore import rescore_dimensions

    seen = {}
    def fake_load():
        seen["called"] = True
        return dataclasses.replace(DEFAULT_PARAMS, base_k=0.3)
    monkeypatch.setattr(grade_formula, "load_params", fake_load)

    rescore_dimensions([], set())
    assert seen.get("called") is True


# --- Task 8: pure compute / preview / apply ---------------------------------

from pathlib import Path  # noqa: E402

from quodeq.core.events.models import Judgment  # noqa: E402
from quodeq.data.projection.grade_projector import (  # noqa: E402
    compute_run_grades,
    recompute_grades,
)
from quodeq.data.sqlite.state_store import SQLiteStateStore  # noqa: E402

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
    import shutil

    project_dir = tmp_path / "proj-uuid"
    project_dir.mkdir()
    run_dir = project_dir / "run1"
    shutil.move(str(_make_run(tmp_path)), str(run_dir))
    legacy = project_dir / "run0"
    legacy.mkdir()  # no events.jsonl → must be skipped

    grade_formula.save_params(_STRICT)
    count = grade_formula.apply_to_all_runs(tmp_path)
    assert count == 1


def test_apply_to_all_runs_clears_cache_when_root_missing(formula_path, monkeypatch, tmp_path):
    """Cache is cleared even when reports_root doesn't exist (returns 0)."""
    cleared = {"called": False}
    import quodeq.services.dashboard as dashboard

    def fake_clear():
        cleared["called"] = True
    monkeypatch.setattr(dashboard, "clear_shared_dimension_cache", fake_clear)

    count = grade_formula.apply_to_all_runs(tmp_path / "does-not-exist")
    assert count == 0
    assert cleared["called"] is True


def test_preview_scores_reads_only_and_reports_before_after(tmp_path, formula_path):
    import shutil

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
