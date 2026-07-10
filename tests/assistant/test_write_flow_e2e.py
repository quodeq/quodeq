# tests/assistant/test_write_flow_e2e.py
"""Full write flow: granted turn edits the worktree, apply lands it in the repo."""
from pathlib import Path

from quodeq.assistant.orchestrator import TurnRequest, run_turn
from quodeq.assistant.tools import ToolContext
from quodeq.assistant.worktree import WorktreeManager, _run
from quodeq.data.sqlite.assistant_repository import AssistantRepository


def test_edit_diff_apply_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_WORKTREES_DIR", str(tmp_path / "wts"))
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "-C", str(repo), "init", "-q", "-b", "main"])
    _run(["git", "-C", str(repo), "config", "user.name", "T"])
    _run(["git", "-C", str(repo), "config", "user.email", "t@example.com"])
    (repo / "app.py").write_bytes(b"x = 1\n")
    _run(["git", "-C", str(repo), "add", "-A"])
    _run(["git", "-C", str(repo), "commit", "-q", "-m", "init"])

    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama", project_id="proj")
    ctx = ToolContext(
        repository=store, session_id="s1", run_dir=None, repo_root=repo,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json", project_id="proj")

    def scripted_model_turn(*, messages, config, registry, emit):
        # the "model": edit a file, self-review the diff, report done
        out = registry.dispatch("edit_repo_file", {
            "path": "app.py", "old_string": "x = 1", "new_string": "x = 2"})
        assert out["ok"], out
        diff = registry.dispatch("get_worktree_diff", {})
        assert "+x = 2" in diff["result"]["diff"]
        return "fixed"

    run_turn(
        TurnRequest(session_id="s1", text="fix it", ui_state=None,
                    api_base="http://x", api_key=None, provider="ollama",
                    model="m", write_enabled=True),
        repository=store, tool_ctx=ctx, turn_fn=scripted_model_turn,
        capability_fn=lambda *a: True)

    # the user's tree is still untouched
    assert (repo / "app.py").read_bytes() == b"x = 1\n"
    # human integration: apply
    row = store.get_worktree("s1")
    manager = WorktreeManager(repo_root=repo, path=Path(row["path"]),
                              branch=row["branch"])
    manager.apply_to_repo()
    assert (repo / "app.py").read_bytes() == b"x = 2\n"
    # and no error frame was emitted during the turn
    frames = [f for _, f in store.events_after("s1", 0)]
    assert not [f for f in frames if f.get("type") == "error"]
