"""Assistant workspace routes: status/diff, apply, discard, PR and their error codes."""
from tests.api._assistant_workspace_fixtures import (  # noqa: F401 -- app/client/repo are pytest fixtures
    _session_with_worktree,
    app,
    client,
    repo,
)


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
    state = app.extensions["assistant_turns"]
    assert state.try_claim_turn(sid)
    try:
        resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
        assert resp.status_code == 409
        assert manager.path.exists()
        assert store.get_worktree(sid)["status"] == "active"
    finally:
        state.release_turn(sid)


def test_discard_claims_turn_slot_and_releases(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    state = app.extensions["assistant_turns"]
    from quodeq.assistant.worktree import WorktreeManager
    seen = {}
    orig = WorktreeManager.remove

    def spy(self, delete_branch=True):
        seen["claimed"] = state.is_turn_claimed(sid)
        return orig(self, delete_branch=delete_branch)

    monkeypatch.setattr(WorktreeManager, "remove", spy)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 200 and seen["claimed"] is True
    assert not state.is_turn_claimed(sid)  # released after


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
    state = app.extensions["assistant_turns"]
    assert state.try_claim_turn(sid)
    try:
        resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
        assert resp.status_code == 409
        assert store.get_worktree(sid)["status"] == "active"
    finally:
        state.release_turn(sid)


def test_apply_claims_turn_slot_during_apply_and_releases(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    state = app.extensions["assistant_turns"]
    from quodeq.assistant.worktree import WorktreeManager
    seen = {}
    orig = WorktreeManager.apply_to_repo

    def spy(self):
        seen["claimed"] = state.is_turn_claimed(sid)
        return orig(self)
    monkeypatch.setattr(WorktreeManager, "apply_to_repo", spy)
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 200 and seen["claimed"] is True
    assert not state.is_turn_claimed(sid)  # released after


def test_apply_survives_remove_failure(app, client, repo, monkeypatch):
    sid, store, _ = _session_with_worktree(app, client, repo)
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    monkeypatch.setattr(WorktreeManager, "remove",
                        lambda self, delete_branch=True: (_ for _ in ()).throw(WorktreeError("busy")))
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 200 and resp.get_json()["applied"] is True
    assert (repo / "app.py").read_bytes() == b"x = 2\n"      # patch landed
    assert store.get_worktree(sid)["status"] == "applied"    # status advanced, no 500


def test_diff_fetch_failure_has_code(app, client, repo, monkeypatch):
    sid, _, _ = _session_with_worktree(app, client, repo)
    from quodeq.assistant.worktree import WorktreeError
    monkeypatch.setattr(
        "quodeq.api.assistant_workspace_routes.diff_text",
        lambda path: (_ for _ in ()).throw(
            WorktreeError("fatal: /Users/marche000/secret-repo: permission denied")))
    resp = client.get(f"/api/assistant/sessions/{sid}/workspace/diff")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == "WORKSPACE_DIFF_FAILED"
    assert "/Users/marche000/secret-repo" not in body["error"]


def test_turn_in_progress_has_code(app, client, repo):
    sid, _, _ = _session_with_worktree(app, client, repo)
    state = app.extensions["assistant_turns"]
    assert state.try_claim_turn(sid)
    try:
        resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "TURN_IN_PROGRESS"
    finally:
        state.release_turn(sid)


def test_discard_failure_has_code(app, client, repo, monkeypatch):
    sid, _, _ = _session_with_worktree(app, client, repo)
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    monkeypatch.setattr(
        WorktreeManager, "remove",
        lambda self, delete_branch=True: (_ for _ in ()).throw(
            WorktreeError("fatal: /Users/marche000/secret-repo: permission denied")))
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == "WORKSPACE_DISCARD_FAILED"
    assert "/Users/marche000/secret-repo" not in body["error"]


def test_apply_failure_has_code(app, client, repo, monkeypatch):
    sid, _, _ = _session_with_worktree(app, client, repo)
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    monkeypatch.setattr(
        WorktreeManager, "apply_to_repo",
        lambda self: (_ for _ in ()).throw(
            WorktreeError("fatal: /Users/marche000/secret-repo: permission denied")))
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "WORKSPACE_APPLY_FAILED"
    assert "/Users/marche000/secret-repo" not in body["error"]


def test_pr_failure_has_code(app, client, repo, monkeypatch):
    sid, _, _ = _session_with_worktree(app, client, repo)
    from quodeq.assistant.worktree import WorktreeError, WorktreeManager
    monkeypatch.setattr(
        WorktreeManager, "create_pr",
        lambda self, title, body: (_ for _ in ()).throw(
            WorktreeError("fatal: /Users/marche000/secret-repo: permission denied")))
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/pr",
                       json={"title": "t", "body": "b"})
    assert resp.status_code == 500
    data = resp.get_json()
    assert data["code"] == "WORKSPACE_PR_FAILED"
    assert "/Users/marche000/secret-repo" not in data["error"]


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
