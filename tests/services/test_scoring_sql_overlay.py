"""Regression: the SQL grade overlay closes the no-dismissals accumulated seam.

Before the overlay moved into the run-read layer, ``get_project_scores`` for a
project with no dismissed/deleted findings served the *eval-time* JSON grades
forever — even after the user applied a custom grade formula (which rewrites the
SQL grade tables via ``apply_to_all_runs``). The dashboard RUN view used the SQL
grades, but the OVERVIEW (accumulated), TREND, and PROJECT CARD did not, so they
disagreed.

These tests pin the fix: ``read_run_data`` overlays the SQL grade tables for
event-log runs, so accumulated / trend / project-card reads all reflect the
applied formula by construction.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from quodeq.core.events.models import Judgment
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.fs.report_parser.runs import read_run_data
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services import grade_formula
from quodeq.services.dashboard import clear_shared_dimension_cache
from quodeq.services.scoring import get_project_scores

# A formula whose severity weights differ sharply from the default so the
# baked-with-custom-params grade is provably different from the default one.
_STRICT = dataclasses.replace(
    DEFAULT_PARAMS, severity_weight={"critical": 4.0, "major": 6.0, "minor": 0.25},
)


@pytest.fixture
def formula_path(tmp_path, monkeypatch):
    path = tmp_path / "grade_formula.json"
    monkeypatch.setattr(grade_formula, "grade_formula_path", lambda: path)
    return path


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _build_event_log_run(
    project_dir: Path, run_id: str, *, principles: list[dict] | None = None,
) -> Path:
    """Create one complete event-log run: findings, SQL grades, eval JSON, manifest.

    Mirrors the ``_make_run`` fixture style from tests/services/test_grade_formula.py
    but adds the minimum scaffolding ``list_runs`` / ``read_run_data`` need:
    an ``evidence/manifest.json`` (so the run is listed) and an eval JSON per
    dimension (so read_run_data parses a dimension to overlay onto).

    *principles* entries (``{"name":..., "score":..., "grade":...}``) are written
    verbatim into every dimension's eval JSON — the eval-time principle grades
    the SQL overlay matches against by name.
    """
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("")  # event-log marker

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
    # Mark the (empty) event log as fully projected so ensure_projected is a
    # no-op and won't wipe the grades we bake below.
    store.save_projected_size((run_dir / "events.jsonl").stat().st_size)

    # Bake default-params grades — this is the "eval-time" baseline.
    recompute_grades(run_dir, params=DEFAULT_PARAMS)

    # An eval JSON per dimension, carrying the default-params (stale) grade so
    # read_run_data has a dimension to overlay onto.
    default_rows = {r["dimension"]: r for r in store.read_dimension_scores()}
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    for dim, row in default_rows.items():
        (eval_dir / f"{dim}.json").write_text(json.dumps({
            "schema_version": 1,
            "dimension": dim,
            "project": project_dir.name,
            "discipline": "Python",
            "date": "2026-05-23",
            "sourceFileCount": 100,
            "overallScore": f"{row['score']}/10",
            "overallGrade": row["grade"],
            "principles": principles or [],
            "violations": [],
            "compliance": [],
            "totals": {"violationCount": 0, "complianceCount": 0, "severity": {}},
        }), encoding="utf-8")

    # Minimal manifest so list_runs surfaces the run as "complete".
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"language_stats": {}}), encoding="utf-8",
    )
    return run_dir


def test_get_project_scores_reflects_applied_custom_params_without_dismissals(
    tmp_path, formula_path,
):
    """No dismissals → accumulated still reflects the APPLIED custom formula.

    This is the seam ``_rescore_accumulated_response`` left open: it
    early-returns when there are no dismissals, so the fix must come from
    the read layer overlaying the (re-baked) SQL grades.
    """
    reports_root = tmp_path / "reports"
    project = "proj-uuid"
    project_dir = reports_root / project
    run_dir = _build_event_log_run(project_dir, "run1")

    # The default-params baseline grade for security.
    default_rows = {r["dimension"]: r for r in SQLiteStateStore(run_dir).read_dimension_scores()}
    default_security = default_rows["security"]

    # Apply custom params: saves the formula and rewrites every run's SQL grades.
    grade_formula.save_params(_STRICT)
    applied = grade_formula.apply_to_all_runs(reports_root)
    assert applied.rescored == 1

    custom_rows = {r["dimension"]: r for r in SQLiteStateStore(run_dir).read_dimension_scores()}
    custom_security = custom_rows["security"]
    # Sanity: the custom formula actually changed the baked grade.
    assert (custom_security["score"], custom_security["grade"]) != (
        default_security["score"], default_security["grade"]
    )

    result = get_project_scores(reports_root, project, None)
    assert result is not None

    acc_dims = {d["dimension"]: d for d in result["accumulated"]["dimensions"]}
    sec = acc_dims["security"]
    # The accumulated payload must show the CUSTOM grade, not the stale eval-time one.
    assert sec["overallScore"] == f"{custom_security['score']}/10"
    assert sec["overallGrade"] == custom_security["grade"]

    # The trend's latest point must agree too.
    assert result["trend"]
    latest = result["trend"][-1]
    latest_security = next(
        d for d in latest["dimensionDetails"] if d["dimension"] == "security"
    )
    assert latest_security["score"] == custom_security["score"]
    assert latest_security["grade"] == custom_security["grade"]


def test_get_project_scores_serves_default_grades_before_apply(
    tmp_path, formula_path,
):
    """Sanity baseline: before any custom formula, accumulated == baked default."""
    reports_root = tmp_path / "reports"
    project = "proj-uuid"
    project_dir = reports_root / project
    run_dir = _build_event_log_run(project_dir, "run1")
    default_rows = {r["dimension"]: r for r in SQLiteStateStore(run_dir).read_dimension_scores()}

    result = get_project_scores(reports_root, project, None)
    sec = {d["dimension"]: d for d in result["accumulated"]["dimensions"]}["security"]
    assert sec["overallScore"] == f"{default_rows['security']['score']}/10"
    assert sec["overallGrade"] == default_rows["security"]["grade"]


def test_read_run_data_overlays_sql_principle_grades_after_apply(
    tmp_path, formula_path,
):
    """Principle-level overlay: eval-time principle grades whose name matches a
    SQL ``principle_id`` are replaced by the re-baked SQL values after Apply.

    The eval JSON carries deliberately wrong sentinel values so the assertion
    can only pass if the overlay actually substituted the SQL row.
    """
    reports_root = tmp_path / "reports"
    project = "proj-uuid"
    run_dir = _build_event_log_run(
        reports_root / project, "run1",
        # "p1" matches the practice_id of every finding baked into SQL.
        principles=[{"name": "p1", "score": "9.9/10", "grade": "A+"}],
    )

    default_p1 = next(
        r for r in SQLiteStateStore(run_dir).read_principle_grades()
        if r["dimension"] == "security" and r["principle_id"] == "p1"
    )

    grade_formula.save_params(_STRICT)
    assert grade_formula.apply_to_all_runs(reports_root).rescored == 1

    custom_p1 = next(
        r for r in SQLiteStateStore(run_dir).read_principle_grades()
        if r["dimension"] == "security" and r["principle_id"] == "p1"
    )
    # Sanity: the custom formula actually changed the baked principle grade.
    assert (custom_p1["score"], custom_p1["grade"]) != (
        default_p1["score"], default_p1["grade"]
    )

    dims = read_run_data(reports_root, project, "run1")
    security = next(d for d in dims if d.dimension == "security")
    p1 = next(p for p in security.principles if p.principle == "p1")
    assert p1.score == f"{custom_p1['score']}/10"
    assert p1.grade == custom_p1["grade"]


def test_read_run_data_keeps_eval_time_principle_on_name_mismatch(
    tmp_path, formula_path,
):
    """A JSON principle whose name matches no SQL ``principle_id`` falls back
    gracefully: no crash, eval-time values kept, dimension overlay still applied.
    """
    reports_root = tmp_path / "reports"
    project = "proj-uuid"
    run_dir = _build_event_log_run(
        reports_root / project, "run1",
        # SQL only knows principle_id "p1"; this name matches nothing.
        principles=[{"name": "Renamed Principle", "score": "3.3/10", "grade": "D"}],
    )

    grade_formula.save_params(_STRICT)
    assert grade_formula.apply_to_all_runs(reports_root).rescored == 1
    custom_rows = {r["dimension"]: r for r in SQLiteStateStore(run_dir).read_dimension_scores()}

    dims = read_run_data(reports_root, project, "run1")
    security = next(d for d in dims if d.dimension == "security")

    # The dimension-level overlay fired (proves we went through the SQL path,
    # not a no-op early return)...
    assert security.overall_score == f"{custom_rows['security']['score']}/10"
    assert security.overall_grade == custom_rows["security"]["grade"]
    # ...but the unmatched principle kept its eval-time values.
    mismatched = next(
        p for p in security.principles if p.principle == "Renamed Principle"
    )
    assert mismatched.score == "3.3/10"
    assert mismatched.grade == "D"
