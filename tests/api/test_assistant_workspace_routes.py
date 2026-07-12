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
    _run(["git", "-C", str(root), "config", "core.autocrlf", "false"])
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
    assert ws["worktree"]["createdAt"]  # per-worktree key for the diff window id
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


def test_discard_blocked_while_turn_in_flight(app, client, repo):
    # Regression: discard raced apply/pr and in-flight write turns because it
    # was the only mutating workspace route with no turn-slot claim. A held
    # slot must 409 discard and leave the worktree intact.
    sid, store, manager = _session_with_worktree(app, client, repo)
    import quodeq.api.assistant_routes as ar
    with ar._running_lock:
        ar._running_turns.add(sid)
    try:
        resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
        assert resp.status_code == 409
        assert manager.path.exists()
        assert store.get_worktree(sid)["status"] == "active"
    finally:
        with ar._running_lock:
            ar._running_turns.discard(sid)


def test_discard_claims_turn_slot_and_releases(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    import quodeq.api.assistant_routes as ar
    from quodeq.assistant.worktree import WorktreeManager
    seen = {}
    orig = WorktreeManager.remove

    def spy(self, delete_branch=True):
        with ar._running_lock:
            seen["claimed"] = sid in ar._running_turns
        return orig(self, delete_branch=delete_branch)

    monkeypatch.setattr(WorktreeManager, "remove", spy)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 200 and seen["claimed"] is True
    with ar._running_lock:
        assert sid not in ar._running_turns  # released after


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


def test_apply_claims_turn_slot_during_apply_and_releases(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    import quodeq.api.assistant_routes as ar
    from quodeq.assistant.worktree import WorktreeManager
    seen = {}
    orig = WorktreeManager.apply_to_repo
    def spy(self):
        with ar._running_lock:
            seen["claimed"] = sid in ar._running_turns
        return orig(self)
    monkeypatch.setattr(WorktreeManager, "apply_to_repo", spy)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 200 and seen["claimed"] is True
    with ar._running_lock:
        assert sid not in ar._running_turns  # released after


def test_apply_survives_remove_failure(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    monkeypatch.setattr(WorktreeManager, "remove",
                        lambda self, delete_branch=True: (_ for _ in ()).throw(WorktreeError("busy")))
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 200 and resp.get_json()["applied"] is True
    assert (repo / "app.py").read_bytes() == b"x = 2\n"      # patch landed
    assert store.get_worktree(sid)["status"] == "applied"    # status advanced, no 500


def test_workspace_apply_requires_csrf_origin(tmp_path, monkeypatch):
    # These routes MUTATE the user's repo; confirm the app-wide security stack gates them.
    import quodeq.api.security as security
    from flask import Flask
    from quodeq.api._rate_limit import create_rate_limit_store
    from quodeq.api.assistant_routes import register_assistant_routes
    monkeypatch.setattr("quodeq.api.assistant_routes.get_provider_configs",
                        lambda: {"ollama": {"type": "api", "api_base": "http://x/v1"}})
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["ASSISTANT_DB_PATH"] = str(tmp_path / "a.db")
    app.config["STANDARDS_EVALUATORS_DIR"] = str(tmp_path / "e")
    app.config["STANDARDS_COMPILED_DIR"] = str(tmp_path / "c")
    app.config["STANDARDS_DIMENSIONS_FILE"] = str(tmp_path / "d.json")
    # configure_security(app, rate_limit_store, api_key); api_key=None keeps the
    # localhost-only auth path so the test-client (127.0.0.1) clears auth and the
    # failure is specifically the CSRF/Origin 403, not an auth 401.
    security.configure_security(app, create_rate_limit_store(), None)
    register_assistant_routes(app)
    client = app.test_client()
    # cross-origin POST (Origin mismatch) must be rejected by the CSRF check
    resp = client.post("/api/assistant/sessions/x/workspace/apply",
                       headers={"Origin": "http://evil.example"})
    assert resp.status_code == 403
