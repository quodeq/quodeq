import pytest
from flask import Flask

from quodeq.api.assistant_routes import register_assistant_routes
from quodeq.assistant.worktree import ensure_session_worktree, _run
from quodeq.data.sqlite.assistant_repository import AssistantRepository


@pytest.fixture()
def app(tmp_path, monkeypatch):
    catalog = {"ollama": {"type": "api", "api_base": "http://localhost:11434/v1"}}
    monkeypatch.setattr(
        "quodeq.api.assistant_routes.get_provider_configs", lambda: catalog)
    monkeypatch.setenv("QUODEQ_WORKTREES_DIR", str(tmp_path / "wts"))
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["ASSISTANT_DB_PATH"] = str(tmp_path / "assistant.db")
    app.config["STANDARDS_EVALUATORS_DIR"] = str(tmp_path / "evaluators")
    app.config["STANDARDS_COMPILED_DIR"] = str(tmp_path / "compiled")
    app.config["STANDARDS_DIMENSIONS_FILE"] = str(tmp_path / "dimensions.json")
    register_assistant_routes(app)
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


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


def _session_with_worktree(app, client, repo):
    sid = client.post("/api/assistant/sessions",
                      json={"provider": "ollama"}).get_json()["sessionId"]
    store = AssistantRepository(app.config["ASSISTANT_DB_PATH"])
    manager = ensure_session_worktree(store, repo_root=repo, project_id="proj",
                                      session_id=sid)
    (manager.path / "app.py").write_bytes(b"x = 2\n")
    return sid, store, manager


def test_workspace_status_and_diff(app, client, repo):
    sid, _, _ = _session_with_worktree(app, client, repo)
    ws = client.get(f"/api/assistant/sessions/{sid}/workspace").get_json()
    assert ws["worktree"]["filesChanged"] == 1
    diff = client.get(f"/api/assistant/sessions/{sid}/workspace/diff").get_json()
    assert "+x = 2" in diff["diff"]


def test_workspace_unknown_session_404(client):
    assert client.get("/api/assistant/sessions/nope/workspace").status_code == 404


def test_apply_then_replay_guard(app, client, repo):
    sid, store, _ = _session_with_worktree(app, client, repo)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 200 and resp.get_json()["applied"] is True
    assert (repo / "app.py").read_bytes() == b"x = 2\n"
    assert store.get_worktree(sid)["status"] == "applied"
    # replay: a second apply must 409, not double-apply
    assert client.post(f"/api/assistant/sessions/{sid}/workspace/apply").status_code == 409


def test_apply_conflict_409_and_nothing_applied(app, client, repo):
    sid, store, _ = _session_with_worktree(app, client, repo)
    (repo / "app.py").write_bytes(b"x = 3\n")  # user's tree diverged
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 409
    assert (repo / "app.py").read_bytes() == b"x = 3\n"
    assert store.get_worktree(sid)["status"] == "active"  # still reviewable


def test_discard_removes_worktree(app, client, repo):
    sid, store, manager = _session_with_worktree(app, client, repo)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 200
    assert not manager.path.exists()
    assert store.get_worktree(sid)["status"] == "discarded"


def test_pr_fail_soft_keeps_branch(app, client, repo, monkeypatch):
    sid, store, manager = _session_with_worktree(app, client, repo)
    # fixture repo has no origin: push fails, endpoint stays 200 fail-soft
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/pr",
                       json={"title": "t", "body": "b"})
    data = resp.get_json()
    assert resp.status_code == 200 and data["prUrl"] is None
    assert store.get_worktree(sid)["status"] == "active"  # retryable


def test_apply_blocked_while_turn_in_flight(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    import quodeq.api.assistant_routes as ar
    with ar._running_lock:
        ar._running_turns.add(sid)
    try:
        resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
        assert resp.status_code == 409
        assert store.get_worktree(sid)["status"] == "active"
    finally:
        with ar._running_lock:
            ar._running_turns.discard(sid)
