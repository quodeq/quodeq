"""Orchestrator MCP server argument assembly."""
from quodeq.assistant.orchestrator import mcp_server_args
from quodeq.assistant.tools import ToolContext

from ._orchestrator_helpers import _request


def test_mcp_server_args_includes_run_and_repo(setup, tmp_path):
    repo, _ctx = setup
    ctx = ToolContext(
        repository=repo, session_id="s1",
        run_dir=tmp_path / "run", repo_root=tmp_path / "repo",
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
    )
    args = mcp_server_args(_request(), ctx)
    assert "--run-dir" in args
    assert args[args.index("--run-dir") + 1] == str(tmp_path / "run")
    assert "--repo-root" in args
    assert args[args.index("--repo-root") + 1] == str(tmp_path / "repo")


def test_mcp_server_args_omits_run_and_repo_when_unset(setup):
    repo, ctx = setup  # fixture ctx has run_dir=None, repo_root=None
    args = mcp_server_args(_request(), ctx)
    assert "--run-dir" not in args
    assert "--repo-root" not in args


def test_mcp_server_args_includes_project_id_and_reports_dir(setup, tmp_path):
    repo, _ctx = setup
    ctx = ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="selectives", reports_dir=tmp_path / "reports",
    )
    args = mcp_server_args(_request(), ctx)
    assert args[args.index("--project-id") + 1] == "selectives"
    assert args[args.index("--reports-dir") + 1] == str(tmp_path / "reports")


def test_mcp_server_args_omits_project_scope_when_unset(setup):
    repo, ctx = setup  # fixture ctx has project_id=None, reports_dir=None
    args = mcp_server_args(_request(), ctx)
    assert "--project-id" not in args
    assert "--reports-dir" not in args


def test_mcp_args_carry_read_only_and_cache_override(tmp_path):
    from quodeq.assistant import AssistantRepository
    from quodeq.assistant.orchestrator import TurnRequest, mcp_server_args
    from quodeq.assistant.tools import ToolContext
    ctx = ToolContext(
        repository=AssistantRepository(tmp_path / "assistant.db"),
        session_id="s", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path, compiled_dir=tmp_path,
        dimensions_file=tmp_path / "dims.json",
        read_only=True, score_cache_path=tmp_path / "score_cache.db")
    req = TurnRequest(session_id="s", text="hi", ui_state=None, api_base="",
                      api_key=None, provider="claude", model="m")
    args = mcp_server_args(req, ctx)
    assert "--read-only" in args
    assert "--score-cache-override" in args
    assert str(tmp_path / "score_cache.db") in args
