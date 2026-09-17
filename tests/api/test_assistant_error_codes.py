"""Machine-readable error codes across the four assistant route modules
(usability cycle 1, task 1; findings 6023-6031, 7235, 7238, 7239, 7242, 7243,
7248, 7252, 7303, 7306, 7307, 7309).

Every error branch in assistant_action_routes.py, assistant_workspace_routes.py,
assistant_session_routes.py, and assistant_turn_routes.py must return a "code"
field alongside "error" (requirement U-APR-2). Each test below drives the
Flask test client to one such branch and asserts both the HTTP status and the
response's "code".

App/session fixtures and helpers are reused, not copied, from the two route
suites that already build them (mirrors the reuse pattern in
test_assistant_shared_sessions.py):
  - test_assistant_routes.py's bare-Flask ``app``/``client`` (registers all
    four route modules with a deterministic provider catalog) plus its
    ``_repo``, ``_VALID_STANDARD``, and ``_drafted_action_on_shared_session``
    helpers -- imported here as ``action_app``/``action_client`` since a
    worktree-backed ``repo`` fixture of the same name also needs importing.
  - test_assistant_workspace_routes.py's worktree-backed ``app``/``client``/
    ``repo`` plus ``_session_with_worktree`` -- imported as
    ``workspace_app``/``workspace_client``/``workspace_repo`` for the same
    reason.
"""
from __future__ import annotations

import pytest

from tests.api.test_assistant_routes import (
    _VALID_STANDARD,
    _drafted_action_on_shared_session,
    _repo,
)
from tests.api.test_assistant_routes import app as action_app
from tests.api.test_assistant_workspace_routes import _session_with_worktree
from tests.api.test_assistant_workspace_routes import app as workspace_app
from tests.api.test_assistant_workspace_routes import repo as workspace_repo

# Quiet unused-import lint for fixtures that are referenced only by name in
# test function signatures, never called directly.
_ = (action_app, workspace_app, workspace_repo)


# The imported ``client`` fixtures in each source module depend on a fixture
# literally named ``app`` (their own parameter name) -- aliasing ``app`` on
# import does not rewire that internal dependency, so each module's own
# renamed ``app`` fixture needs its own thin client wrapper here instead of
# importing the two conflicting ``client`` fixtures under aliases.
@pytest.fixture()
def action_client(action_app):
    return action_app.test_client()


@pytest.fixture()
def workspace_client(workspace_app):
    return workspace_app.test_client()


# --- assistant_action_routes.py: apply/reject (findings 6023-6031) --------

def _setup_unknown(app, client):
    return "missing"


def _setup_read_only(app, client):
    _drafted_action_on_shared_session(app)
    return "a-ro"


def _setup_already(app, client):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1", action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h")
    assert repo.set_action_status("a1", "applied", expected="drafted")
    return "a1"


def _setup_unsupported(app, client):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1", action_type="totally_bogus_type",
                       payload={}, content_hash="h")
    return "a1"


def _setup_invalid(app, client):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    invalid = {k: v for k, v in _VALID_STANDARD.items() if k != "principles"}
    repo.create_action(action_id="a1", session_id="s1", action_type="create_standard",
                       payload=invalid, content_hash="h")
    return "a1"


def _setup_conflict(app, client):
    repo = _repo(app)
    repo.create_session(session_id="s1", provider="ollama")
    repo.create_action(action_id="a1", session_id="s1", action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h1")
    assert client.post("/api/assistant/actions/a1/apply").status_code == 200
    repo.create_action(action_id="a2", session_id="s1", action_type="create_standard",
                       payload=_VALID_STANDARD, content_hash="h2")
    return "a2"


@pytest.mark.parametrize("route,setup,status,code", [
    ("apply", _setup_unknown, 404, "UNKNOWN_ACTION"),                 # 6023
    ("apply", _setup_read_only, 403, "READ_ONLY_SESSION"),             # 6024
    ("apply", _setup_already, 409, "ACTION_ALREADY_RESOLVED"),        # 6025
    ("apply", _setup_unsupported, 400, "UNSUPPORTED_ACTION_TYPE"),    # 6026
    ("apply", _setup_invalid, 400, "INVALID_ACTION"),                 # 6027
    ("apply", _setup_conflict, 409, "ACTION_CONFLICT"),                # 6028
    ("reject", _setup_unknown, 404, "UNKNOWN_ACTION"),                 # 6029
    ("reject", _setup_read_only, 403, "READ_ONLY_SESSION"),            # 6030
    ("reject", _setup_already, 409, "ACTION_ALREADY_RESOLVED"),       # 6031
])
def test_action_route_error_has_code(action_app, action_client, route, setup, status, code):
    action_id = setup(action_app, action_client)
    resp = action_client.post(f"/api/assistant/actions/{action_id}/{route}")
    assert resp.status_code == status
    assert resp.get_json()["code"] == code


# --- assistant_workspace_routes.py (findings 7235, 7238, 7243, 7248, 7252) -

def test_workspace_unknown_session_has_code(action_client):  # 7235
    resp = action_client.get("/api/assistant/sessions/nope/workspace")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "UNKNOWN_SESSION"


def test_workspace_diff_no_active_worktree_has_code(action_client):  # 7238
    sid = action_client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = action_client.get(f"/api/assistant/sessions/{sid}/workspace/diff")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NO_ACTIVE_WORKTREE"


def test_workspace_apply_conflict_has_code(workspace_app, workspace_client, workspace_repo):  # 7243
    sid, _, _ = _session_with_worktree(workspace_app, workspace_client, workspace_repo)
    assert workspace_client.post(
        f"/api/assistant/sessions/{sid}/workspace/apply").status_code == 200
    resp = workspace_client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "WORKTREE_CONFLICT"


def test_workspace_pr_turn_busy_has_code(workspace_app, workspace_client, workspace_repo):  # 7248
    sid, _, _ = _session_with_worktree(workspace_app, workspace_client, workspace_repo)
    state = workspace_app.extensions["assistant_turns"]
    assert state.try_claim_turn(sid)
    try:
        resp = workspace_client.post(
            f"/api/assistant/sessions/{sid}/workspace/pr", json={"title": "t", "body": "b"})
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "TURN_IN_PROGRESS"
    finally:
        state.release_turn(sid)


def test_workspace_discard_turn_busy_has_code(workspace_app, workspace_client, workspace_repo):  # 7252
    sid, _, _ = _session_with_worktree(workspace_app, workspace_client, workspace_repo)
    state = workspace_app.extensions["assistant_turns"]
    assert state.try_claim_turn(sid)
    try:
        resp = workspace_client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "TURN_IN_PROGRESS"
    finally:
        state.release_turn(sid)


# --- assistant_session_routes.py (findings 7239, 7242) --------------------

def test_create_session_unknown_provider_has_code(action_client):  # 7239
    resp = action_client.post("/api/assistant/sessions", json={"provider": "nope"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_PROVIDER"


def test_create_session_invalid_source_has_code(action_client):  # 7242
    resp = action_client.post(
        "/api/assistant/sessions", json={"provider": "ollama", "source": "cloud"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_SOURCE"


# --- assistant_turn_routes.py (findings 7303, 7306, 7307, 7309) -----------

def test_post_message_unknown_session_has_code(action_client):  # 7303
    resp = action_client.post("/api/assistant/sessions/nope/messages", json={"text": "x"})
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "UNKNOWN_SESSION"


def test_post_message_provider_busy_has_code(action_client, monkeypatch):  # 7306
    monkeypatch.setattr("quodeq.api.assistant_turn_routes.local_provider_busy", lambda p: True)
    sid = action_client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = action_client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "PROVIDER_BUSY"


def test_post_message_turn_already_running_has_code(action_app, action_client):  # 7307
    sid = action_client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    state = action_app.extensions["assistant_turns"]
    assert state.claim_turn(sid) is not None
    try:
        resp = action_client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "hi"})
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "TURN_IN_PROGRESS"
    finally:
        state.release_turn(sid)


def test_events_stream_too_many_streams_has_code(action_app, action_client):  # 7309
    state = action_app.extensions["assistant_turns"]
    sid = action_client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    slots_taken = 0
    while state.try_open_sse_stream():
        slots_taken += 1
    try:
        resp = action_client.get(f"/api/assistant/sessions/{sid}/events?after=0")
        assert resp.status_code == 429
        assert resp.get_json()["code"] == "TOO_MANY_STREAMS"
    finally:
        for _ in range(slots_taken):
            state.close_sse_stream()
