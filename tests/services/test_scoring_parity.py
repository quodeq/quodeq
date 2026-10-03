"""Cross-path scoring parity: every per-run read path agrees on the score.

The regression guard against the disparity where the SAME run+dimension
reported different per-dimension scores depending on which endpoint asked:
- ``get_scores_raw`` (per-run explorer detail)
- ``build_dashboard`` selected run
- ``resolve_dimension_eval`` (dimension detail)
- the dashboard trend's per-run score
- the accumulated block

A dismissal is a project-wide false positive, so all of these must serve the
dismiss-adjusted score, not the raw scan score.
"""
from __future__ import annotations

from quodeq.services.dashboard import build_dashboard, clear_shared_dimension_cache
from quodeq.services.scoring import get_project_scores, get_scores_raw
from quodeq.services.violations import resolve_dimension_eval
from tests.services._scoring_parity_fixtures import (  # noqa: F401 -- _clear_cache is a pytest fixture
    _DIM,
    _RUN,
    _build_run_with_violations,
    _clear_cache,
    _dismiss_and_freeze_sql,
    _num,
    _perf_score,
)


def test_all_read_paths_agree_after_dismissal(tmp_path):
    """Dismissing a finding shifts EVERY per-run read path to the same value."""
    reports_root = tmp_path / "evaluations"
    project = "proj-uuid"
    run_dir = _build_run_with_violations(reports_root, project)
    project_dir = reports_root / project

    # Dismiss the critical finding project-wide and freeze the SQL projection
    # stale, so the run's baked SQL grade stays RAW (the real-world case).
    _dismiss_and_freeze_sql(project_dir, run_dir, {"req": "R1", "file": "a.py", "line": 1})

    # 1. accumulated (already dismiss-adjusted; the reference value).
    gps = get_project_scores(reports_root, project, None)
    accumulated = _perf_score(gps["accumulated"]["dimensions"])
    assert accumulated is not None

    # 2. per-run explorer detail.
    per_run = _perf_score(get_scores_raw(reports_root, project, _RUN)["dimensions"])

    # 3. dashboard selected run.
    db = build_dashboard(str(reports_root), project, _RUN)
    dashboard = _perf_score(db["dimensions"])

    # 4. dimension detail: overall lives in principleGrades[isOverall].
    de = resolve_dimension_eval(project_dir / _RUN, project, _RUN, _DIM)
    overall_pg = next(pg for pg in de["principleGrades"] if pg.get("isOverall"))
    dim_eval = overall_pg["score"]

    # 5. trend per-run score for this run.
    trend_point = next(t for t in gps["trend"] if t["runId"] == _RUN)
    trend_detail = next(d for d in trend_point["dimensionDetails"] if d["dimension"] == _DIM)
    trend = trend_detail["score"]  # numeric

    assert _num(per_run) == _num(accumulated), f"per-run {per_run} != accumulated {accumulated}"
    assert _num(dashboard) == _num(accumulated), f"dashboard {dashboard} != accumulated {accumulated}"
    assert _num(dim_eval) == _num(accumulated), f"dim-eval {dim_eval} != accumulated {accumulated}"
    assert trend == _num(accumulated), f"trend {trend} != accumulated {accumulated}"

    # Also assert grade parity where each path exposes one.
    acc_grade = next(
        d["overallGrade"] for d in gps["accumulated"]["dimensions"] if d["dimension"] == _DIM
    )
    assert overall_pg["grade"] == acc_grade


def test_project_card_summary_applies_deletions(tmp_path, monkeypatch):
    """The repositories-card grade must apply project-wide DELETIONS, agreeing
    with the accumulated / scored per-run paths.

    Regression: ``read_accumulated_summary`` (the project-card path) read raw
    ``read_run_data`` and never applied the project-wide dismiss/delete rescore
    that every other read path routes through (``scored_run_dimensions``). So a
    project with deletions showed a stale, too-low card grade on the
    repositories screen while the Overview / explorer / trend showed the higher,
    deletion-adjusted score. Deletions never appear in the SQL grade overlay, so
    this path missed them entirely.
    """
    reports_root = tmp_path / "evaluations"
    project = "proj-uuid"
    _build_run_with_violations(reports_root, project)
    project_dir = reports_root / project
    # Isolate the project-summary cache so a real ~/.quodeq cache can't leak in.
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))

    from quodeq.services._fs_metadata import read_accumulated_summary
    from quodeq.services.deleted import delete_finding
    from quodeq.data.fs.report_parser.runs import list_runs

    # Delete the critical finding project-wide — this raises the score.
    delete_finding(project_dir, {"dimension": _DIM, "principle": "p1", "file": "a.py"})
    clear_shared_dimension_cache()

    # Reference: the accumulated view is deletion-adjusted.
    gps = get_project_scores(reports_root, project, None)
    accumulated = _num(_perf_score(gps["accumulated"]["dimensions"]))
    assert accumulated is not None

    # The project-card summary must serve the SAME deletion-adjusted score.
    # compute_on_miss=True: this test exercises the rescore-parity logic
    # itself, not the local list path's cache-only/pending contract.
    runs = list_runs(reports_root, project)
    _grade, card_score, _files, _pending = read_accumulated_summary(
        reports_root, project, runs, compute_on_miss=True)
    assert card_score == accumulated, f"card {card_score} != accumulated {accumulated}"


def test_deletion_actually_moves_the_card_score(tmp_path, monkeypatch):
    """Guard: the deletion genuinely raises the card score (else parity is trivial)."""
    reports_root = tmp_path / "evaluations"
    project = "proj-uuid2"
    _build_run_with_violations(reports_root, project)
    project_dir = reports_root / project
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))

    from quodeq.services._fs_metadata import read_accumulated_summary
    from quodeq.services.deleted import delete_finding
    from quodeq.data.fs.report_parser.runs import list_runs

    # compute_on_miss=True: see test_project_card_summary_applies_deletions.
    runs = list_runs(reports_root, project)
    _g, before, _f, _p = read_accumulated_summary(
        reports_root, project, runs, compute_on_miss=True)
    delete_finding(project_dir, {"dimension": _DIM, "principle": "p1", "file": "a.py"})
    clear_shared_dimension_cache()
    _g2, after, _f2, _p2 = read_accumulated_summary(
        reports_root, project, runs, compute_on_miss=True)
    assert before is not None and after is not None
    assert after > before, f"deleting the critical should raise the card score; {before} -> {after}"


def test_dismissal_actually_moves_the_score(tmp_path):
    """Guard: the fixture's dismissal genuinely changes the score.

    Without this, the parity test could pass trivially if every path served the
    same RAW value (i.e. the dismiss had no effect at all).
    """
    reports_root = tmp_path / "evaluations"
    project = "proj-uuid"
    run_dir = _build_run_with_violations(reports_root, project)
    project_dir = reports_root / project

    before = _perf_score(get_scores_raw(reports_root, project, _RUN)["dimensions"])
    _dismiss_and_freeze_sql(project_dir, run_dir, {"req": "R1", "file": "a.py", "line": 1})
    clear_shared_dimension_cache()
    after = _perf_score(get_scores_raw(reports_root, project, _RUN)["dimensions"])

    assert _num(after) is not None and _num(before) is not None
    assert _num(after) > _num(before), f"dismissing the critical should raise the score; {before} -> {after}"
