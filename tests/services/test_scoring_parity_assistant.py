"""Cross-path scoring parity for the assistant read tools: dismiss-adjusted scores and action-scope identity."""
from __future__ import annotations

from pathlib import Path

from quodeq.services.scoring import get_project_scores
from tests.services._scoring_parity_fixtures import (  # noqa: F401 -- _clear_cache is a pytest fixture
    _DIM,
    _build_run_with_violations,
    _clear_cache,
    _dismiss_and_freeze_sql,
    _num,
    _perf_score,
)


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
    scores = run_reg.dispatch("get_scores", {})["result"]["scores"]
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
    over_scores = over_reg.dispatch("get_scores", {})["result"]["scores"]
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
