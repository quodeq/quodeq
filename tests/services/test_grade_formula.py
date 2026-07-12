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


# --- Regression: run ordering must use started_at, not dir mtime -------------

import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402


def _write_status_json(run_dir: Path, started_at: str) -> None:
    """Write a minimal valid status.json fixture into *run_dir*."""
    payload = {
        "schema_version": 2,
        "job_id": run_dir.name,
        "state": "done",
        "started_at": started_at,
        "updated_at": started_at,
        "finalized_at": started_at,
        "phase": None,
        "current_dimension": None,
        "dimensions": [],
        "pid": 1,
        "exit_reason": None,
        "deadline_at": None,
    }
    (run_dir / "status.json").write_text(json.dumps(payload), encoding="utf-8")


def test_event_log_runs_orders_by_started_at_not_mtime(tmp_path):
    """Older started_at run must not win just because its dir mtime is bumped.

    Scenario: run_old was created earlier (lower started_at) but we
    artificially advance its directory mtime so it looks newer to a naive
    mtime sort.  _event_log_runs must still return run_new first.
    """
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    run_old = project_dir / "run_old"
    run_old.mkdir()
    (run_old / "events.jsonl").write_text("")
    _write_status_json(run_old, "2024-01-01T10:00:00+00:00")

    run_new = project_dir / "run_new"
    run_new.mkdir()
    (run_new / "events.jsonl").write_text("")
    _write_status_json(run_new, "2024-06-01T10:00:00+00:00")

    # Bump run_old's mtime to "now + 1 hour" so a naive mtime sort would pick it.
    future_ts = time.time() + 3600
    os.utime(run_old, (future_ts, future_ts))

    from quodeq.services.grade_formula import _event_log_runs  # noqa: PLC0415

    ordered = _event_log_runs(project_dir)
    assert ordered[0] == run_new, (
        f"Expected run_new (newer started_at) first, got {ordered[0].name}"
    )


# --- Regression: UnsupportedSchemaError must not crash run ordering ----------

def test_event_log_runs_tolerates_future_schema_version(tmp_path):
    """A run whose status.json has a schema_version newer than supported must
    not raise; it falls back to mtime ordering and the other runs are unaffected.
    """
    from quodeq.shared.run_status import SCHEMA_VERSION
    from quodeq.services.grade_formula import _event_log_runs  # noqa: PLC0415

    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    # A normal run with a known-good status.json.
    run_good = project_dir / "run_good"
    run_good.mkdir()
    (run_good / "events.jsonl").write_text("")
    _write_status_json(run_good, "2024-06-01T10:00:00+00:00")

    # A run with a status.json whose schema_version is far above supported.
    run_future = project_dir / "run_future"
    run_future.mkdir()
    (run_future / "events.jsonl").write_text("")
    future_payload = {
        "schema_version": SCHEMA_VERSION + 99,
        "job_id": "run_future",
        "state": "done",
        "started_at": "2024-03-01T10:00:00+00:00",
    }
    (run_future / "status.json").write_text(json.dumps(future_payload), encoding="utf-8")

    # Must not raise — and both runs must be present in the result.
    ordered = _event_log_runs(project_dir)
    names = [r.name for r in ordered]
    assert "run_good" in names, "run_good must be included"
    assert "run_future" in names, "run_future must be included (mtime fallback)"
    # run_good has a proper started_at key (priority 1); run_future uses mtime
    # fallback (priority 0) so run_good always sorts first regardless of mtime.
    assert ordered[0].name == "run_good", (
        f"run_good (proper started_at) should sort first, got {ordered[0].name}"
    )
