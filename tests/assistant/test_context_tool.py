from pathlib import Path

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.data.sqlite.assistant_repository import AssistantRepository


def _ctx(tmp_path, *, project_id="project-1", run_dir=None, repo_root=None, reports_dir=None):
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="codex", model="5.5")
    return ToolContext(
        repository=repo,
        session_id="s1",
        run_dir=Path(run_dir) if run_dir is not None else None,
        repo_root=Path(repo_root) if repo_root is not None else None,
        evaluators_dir=tmp_path / "evaluators",
        compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        project_id=project_id,
        reports_dir=Path(reports_dir) if reports_dir is not None else tmp_path / "reports",
    )


def test_get_context_reports_overview_scope(tmp_path):
    out = build_registry(_ctx(tmp_path)).dispatch("get_context", {})

    assert out["ok"] is True
    result = out["result"]
    assert result["projectId"] == "project-1"
    assert result["runSelected"] is False
    assert result["repoAttached"] is False
    assert result["overviewAvailable"] is True
    assert "get_overview" in result["guidance"]


def test_get_context_reports_run_and_repo_scope(tmp_path):
    run_dir = tmp_path / "reports" / "project-1" / "run-1"
    repo_root = tmp_path / "repo"
    run_dir.mkdir(parents=True)
    repo_root.mkdir()

    out = build_registry(_ctx(
        tmp_path, run_dir=run_dir, repo_root=repo_root,
    )).dispatch("get_context", {})["result"]

    assert out["runSelected"] is True
    assert out["runDirAttached"] is True
    assert out["repoAttached"] is True
    assert out["runId"] == "run-1"
    assert "read_repo_file" in out["guidance"]


def test_get_context_reports_missing_scope(tmp_path):
    out = build_registry(_ctx(
        tmp_path, project_id=None, reports_dir=None,
    )).dispatch("get_context", {})["result"]

    assert out["projectId"] is None
    assert out["overviewAvailable"] is False
    assert out["guidance"] == "No project or run is attached; ask the user to open a project overview or run."
