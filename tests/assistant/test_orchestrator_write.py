import pytest

from quodeq.assistant.orchestrator import TurnRequest, run_turn
from quodeq.assistant.tools import ToolContext
from quodeq.assistant.worktree import _run
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _run(["git", "-C", str(root), "init", "-q", "-b", "main"])
    _run(["git", "-C", str(root), "config", "user.name", "T"])
    _run(["git", "-C", str(root), "config", "user.email", "t@example.com"])
    (root / "app.py").write_bytes(b"x = 1\n")
    _run(["git", "-C", str(root), "add", "-A"])
    _run(["git", "-C", str(root), "commit", "-q", "-m", "init"])
    return root


def _fixture(tmp_path, repo_root, monkeypatch):
    monkeypatch.setenv("QUODEQ_WORKTREES_DIR", str(tmp_path / "wts"))
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama", project_id="proj")
    ctx = ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=repo_root,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json", project_id="proj")
    return store, ctx


def _request(write_enabled):
    return TurnRequest(session_id="s1", text="hi", ui_state=None,
                       api_base="http://x", api_key=None, provider="ollama",
                       model="m", write_enabled=write_enabled)


def _capture_turn(seen):
    def fake_turn(*, messages, config, registry, emit):
        seen["names"] = registry.names()
        seen["iters"] = config.max_tool_iterations
        seen["system"] = messages[0]["content"]
        return "ok"
    return fake_turn


def test_write_grant_registers_tools_and_creates_worktree(tmp_path, repo, monkeypatch):
    store, ctx = _fixture(tmp_path, repo, monkeypatch)
    seen = {}
    run_turn(_request(True), repository=store, tool_ctx=ctx,
             turn_fn=_capture_turn(seen), capability_fn=lambda *a: True)
    assert "edit_repo_file" in seen["names"]
    assert seen["iters"] >= 16
    assert "# Write access" in seen["system"]
    row = store.get_worktree("s1")
    assert row is not None and row["status"] == "active"


def test_no_grant_no_write_tools(tmp_path, repo, monkeypatch):
    store, ctx = _fixture(tmp_path, repo, monkeypatch)
    seen = {}
    run_turn(_request(False), repository=store, tool_ctx=ctx,
             turn_fn=_capture_turn(seen), capability_fn=lambda *a: True)
    assert "edit_repo_file" not in seen["names"]
    assert store.get_worktree("s1") is None


def test_grant_without_git_repo_stays_read_only(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    store, ctx = _fixture(tmp_path, plain, monkeypatch)
    seen = {}
    run_turn(_request(True), repository=store, tool_ctx=ctx,
             turn_fn=_capture_turn(seen), capability_fn=lambda *a: True)
    assert "edit_repo_file" not in seen["names"]


def test_cli_branch_passes_write_args(tmp_path, repo, monkeypatch):
    store, ctx = _fixture(tmp_path, repo, monkeypatch)
    seen = {}

    def fake_cli_turn(*, messages, config, session_id, prior_session_id,
                      repository, emit):
        seen["args"] = config.mcp_server_args
        seen["worktree_dir"] = config.worktree_dir
        return "ok"

    monkeypatch.setattr("quodeq.assistant.orchestrator._provider_type",
                        lambda p: "cli")
    run_turn(_request(True), repository=store, tool_ctx=ctx,
             turn_fn=None, cli_turn_fn=fake_cli_turn)
    assert "--enable-write" in seen["args"]
    assert "--worktree-dir" in seen["args"]
    assert seen["worktree_dir"] is not None
