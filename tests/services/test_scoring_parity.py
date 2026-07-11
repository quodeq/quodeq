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

import json
from pathlib import Path

import pytest

from quodeq.core.events.models import Judgment
from quodeq.data.projection.grade_projector import recompute_grades
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.data.sqlite.state_store import SQLiteStateStore
from quodeq.services.dashboard import build_dashboard, clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding
from quodeq.services.scoring import get_project_scores, get_scores_raw
from quodeq.services.violations import resolve_dimension_eval


def _dismiss_and_freeze_sql(project_dir: Path, run_dir: Path, finding: dict) -> None:
    """Dismiss a finding project-wide, then freeze the SQL projection stale.

    On real data, a run's baked SQL ``dimension_scores`` do NOT reflect
    project-wide dismissals that accrued after the scan: the actions-log size
    is already checkpointed, so re-projection is a no-op and the SQL grade
    stays RAW. We reproduce that here by advancing the run's
    ``actions_projected_size`` checkpoint to the current actions.jsonl size, so
    ``ensure_projected`` skips re-applying the dismissal to SQL. This is what
    forces ``get_scores_raw``'s SQL fast path to serve the raw score unless it
    routes through the project-wide rescore -- the exact real-world failure.
    """
    dismiss_finding(project_dir, finding)
    actions_log = project_dir / "actions.jsonl"
    size = actions_log.stat().st_size if actions_log.is_file() else 0
    SQLiteStateStore(run_dir).save_actions_projected_size(size)

_DIM = "performance"
_RUN = "20260101T000000"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _build_run_with_violations(reports_root: Path, project: str) -> Path:
    """One complete event-log run whose eval JSON carries real violations.

    Findings are baked into SQL (so read_dimension_scores / the SQL fast path
    have real grades) AND written into the eval JSON's ``violations`` array (so
    read_run_data -> _rescore_dimension sees them and a project-wide dismiss can
    move the score). This is what makes the raw vs dismiss-adjusted score differ.
    """
    run_dir = reports_root / project / _RUN
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("")

    store = SQLiteStateStore(run_dir)
    violations = [
        Judgment(
            practice_id="p1", dimension=_DIM, req="R1", verdict="violation",
            severity="critical", file="a.py", line=1, title="crit", reason="null deref",
        ),
        *[
            Judgment(
                practice_id="p1", dimension=_DIM, req=f"R{i}", verdict="violation",
                severity="major", file=f"f{i}.py", line=10, title=f"t{i}", reason=f"r{i}",
            )
            for i in range(2, 6)
        ],
    ]
    compliance = [
        Judgment(
            practice_id="p1", dimension=_DIM, req=f"C{i}", verdict="compliance",
            severity="minor", file=f"c{i}.py", line=20, title=f"ct{i}", reason=f"cr{i}",
        )
        for i in range(6)
    ]
    for f in [*violations, *compliance]:
        store.record_finding(f)
    store.save_projected_size((run_dir / "events.jsonl").stat().st_size)
    recompute_grades(run_dir, params=DEFAULT_PARAMS)

    row = {r["dimension"]: r for r in store.read_dimension_scores()}[_DIM]
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{_DIM}.json").write_text(json.dumps({
        "schema_version": 1, "dimension": _DIM, "project": project,
        "discipline": "Python", "date": "2026-05-23", "sourceFileCount": 100,
        "overallScore": f"{row['score']}/10", "overallGrade": row["grade"],
        "principles": [{"name": "p1", "score": f"{row['score']}/10", "grade": row["grade"]}],
        "violations": [
            {
                # The parser maps ``practice_id`` from the ``principle`` key, so
                # carry both — deletions key on (dimension, principle, file).
                "practiceId": v.practice_id, "principle": v.practice_id,
                "req": v.req, "file": v.file, "line": v.line,
                "severity": v.severity, "title": v.title, "reason": v.reason,
            }
            for v in violations
        ],
        "compliance": [
            {
                "practiceId": c.practice_id, "req": c.req, "file": c.file, "line": c.line,
                "severity": c.severity, "title": c.title, "reason": c.reason,
            }
            for c in compliance
        ],
        "totals": {
            "violationCount": len(violations), "complianceCount": len(compliance),
            "severity": {"critical": 1, "major": 4, "minor": 0},
        },
    }), encoding="utf-8")

    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.json").write_text(
        json.dumps({"language_stats": {}}), encoding="utf-8")
    return run_dir


def _perf_score(dims) -> str | None:
    for d in dims:
        name = d.get("dimension") if isinstance(d, dict) else getattr(d, "dimension", None)
        if name == _DIM:
            return d.get("overallScore") if isinstance(d, dict) else getattr(d, "overall_score", None)
    return None


def _num(score: str | None) -> float | None:
    if not score or "/" not in str(score):
        return None
    return float(str(score).split("/")[0])


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

    Regression: ``_read_accumulated_summary`` (the project-card path) read raw
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

    from quodeq.services._fs_metadata import _read_accumulated_summary
    from quodeq.services.deleted import delete_finding
    from quodeq.services.ports import list_runs

    # Delete the critical finding project-wide — this raises the score.
    delete_finding(project_dir, {"dimension": _DIM, "principle": "p1", "file": "a.py"})
    clear_shared_dimension_cache()

    # Reference: the accumulated view is deletion-adjusted.
    gps = get_project_scores(reports_root, project, None)
    accumulated = _num(_perf_score(gps["accumulated"]["dimensions"]))
    assert accumulated is not None

    # The project-card summary must serve the SAME deletion-adjusted score.
    runs = list_runs(reports_root, project)
    _grade, card_score, _files = _read_accumulated_summary(reports_root, project, runs)
    assert card_score == accumulated, f"card {card_score} != accumulated {accumulated}"


def test_deletion_actually_moves_the_card_score(tmp_path, monkeypatch):
    """Guard: the deletion genuinely raises the card score (else parity is trivial)."""
    reports_root = tmp_path / "evaluations"
    project = "proj-uuid2"
    _build_run_with_violations(reports_root, project)
    project_dir = reports_root / project
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "score_cache.db"))

    from quodeq.services._fs_metadata import _read_accumulated_summary
    from quodeq.services.deleted import delete_finding
    from quodeq.services.ports import list_runs

    runs = list_runs(reports_root, project)
    _g, before, _f = _read_accumulated_summary(reports_root, project, runs)
    delete_finding(project_dir, {"dimension": _DIM, "principle": "p1", "file": "a.py"})
    clear_shared_dimension_cache()
    _g2, after, _f2 = _read_accumulated_summary(reports_root, project, runs)
    assert before is not None and after is not None
    assert after > before, f"deleting the critical should raise the card score; {before} -> {after}"


def _assistant_ctx(tmp_path, reports_root: Path, project: str, run_dir: Path | None):
    """A real assistant ToolContext over the parity fixture's project."""
    from quodeq.assistant.tools import ToolContext
    from quodeq.data.sqlite.assistant_repository import AssistantRepository

    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id=project, reports_dir=reports_root,
    )


def test_assistant_tools_agree_after_dismissal(tmp_path):
    """The assistant's read tools serve the dismiss-adjusted score everywhere.

    Regression: the assistant tool layer was another missed read path in the
    same class as the dashboard/trend/card disparities. ``get_scores`` /
    ``get_report`` / ``get_violations`` (run scope) read the raw eval JSON, and
    the accumulated scope plus ``get_overview`` read ``compute_accumulated``
    WITHOUT the project-wide rescore -- so the assistant quoted raw pre-triage
    scores (and re-surfaced dismissed findings) while the Overview showed the
    dismiss-adjusted grade.
    """
    from dataclasses import replace as dc_replace

    from quodeq.assistant.tools import build_registry

    reports_root = tmp_path / "evaluations"
    project = "proj-uuid"
    run_dir = _build_run_with_violations(reports_root, project)
    _dismiss_and_freeze_sql(
        reports_root / project, run_dir, {"req": "R1", "file": "a.py", "line": 1})

    # Reference: the Overview's dismiss-adjusted accumulated score.
    gps = get_project_scores(reports_root, project, None)
    accumulated = _num(_perf_score(gps["accumulated"]["dimensions"]))
    assert accumulated is not None

    # Run scope: get_scores / get_report / get_violations.
    run_ctx = _assistant_ctx(tmp_path, reports_root, project, run_dir)
    run_reg = build_registry(run_ctx)
    scores = run_reg.dispatch("get_scores", {})["result"]
    assert _num(scores[_DIM]["score"]) == accumulated, (
        f"assistant run-scope get_scores {scores[_DIM]['score']} != accumulated {accumulated}")

    report = run_reg.dispatch("get_report", {"dimension": _DIM})["result"]
    assert _num(report["overallScore"]) == accumulated
    assert not any(v["file"] == "a.py" and v["line"] == 1 for v in report["violations"]), (
        "dismissed finding must not resurface in assistant get_report")

    viols = run_reg.dispatch("get_violations", {"dimension": _DIM})["result"]
    assert viols["count"] == 4, "get_violations must exclude the dismissed finding"

    # Overview (accumulated) scope: get_scores + get_overview.
    over_ctx = dc_replace(run_ctx, run_dir=None)
    over_reg = build_registry(over_ctx)
    over_scores = over_reg.dispatch("get_scores", {})["result"]
    assert _num(over_scores[_DIM]["score"]) == accumulated, (
        f"assistant overview get_scores {over_scores[_DIM]['score']} != accumulated {accumulated}")

    overview = over_reg.dispatch("get_overview", {})["result"]
    over_dim = next(d for d in overview["dimensions"] if d["dimension"] == _DIM)
    assert _num(over_dim["score"]) == accumulated, (
        f"assistant get_overview {over_dim['score']} != accumulated {accumulated}")


def test_dismissed_finding_stays_in_assistant_action_scope(tmp_path):
    """Rescoring the read tools must NOT hide dismissed findings from the
    dismiss/verify identity check -- ``finding_keys_in_scope`` keeps reading the
    raw sources so an action targeting an already-dismissed finding still
    matches (idempotent re-dismiss / verify)."""
    from quodeq.assistant.tools._read_tools import finding_keys_in_scope

    reports_root = tmp_path / "evaluations"
    project = "proj-uuid"
    run_dir = _build_run_with_violations(reports_root, project)
    _dismiss_and_freeze_sql(
        reports_root / project, run_dir, {"req": "R1", "file": "a.py", "line": 1})

    run_ctx = _assistant_ctx(tmp_path, reports_root, project, run_dir)
    assert ("R1", "a.py", 1) in finding_keys_in_scope(run_ctx)


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
