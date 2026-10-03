"""Machine-readable error-code coverage for assistant_workspace_routes.py's
remaining bare sites: tools/check_error_codes.py's zero-tolerance gate found
the "no worktree" 404s on apply/pr/discard, discard's "gone" race, and the
"worktree already <status>" 409 on pr/discard.

Sibling of test_assistant_workspace_routes.py, which is already over the
300-line file cap (grandfathered) -- new coverage goes in a new file
instead of growing it further. Fixtures are reused, not copied, from there.
"""
from __future__ import annotations

from quodeq.assistant.workspace_actions import DiscardOutcome
from tests.api.test_assistant_workspace_routes import _session_with_worktree
from tests.api.test_assistant_workspace_routes import app  # noqa: F401 -- pytest fixture
from tests.api.test_assistant_workspace_routes import client  # noqa: F401 -- pytest fixture
from tests.api.test_assistant_workspace_routes import repo  # noqa: F401 -- pytest fixture


def test_apply_no_worktree_has_code(app, client):
    sid = client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/apply")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NO_ACTIVE_WORKTREE"


def test_pr_no_worktree_has_code(app, client):
    sid = client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = client.post(
        f"/api/assistant/sessions/{sid}/workspace/pr", json={"title": "t", "body": "b"})
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NO_ACTIVE_WORKTREE"


def test_discard_no_worktree_has_code(app, client):
    sid = client.post(
        "/api/assistant/sessions", json={"provider": "ollama"}).get_json()["sessionId"]
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NO_ACTIVE_WORKTREE"


def test_discard_gone_has_code(app, client, repo, monkeypatch):
    sid, _, _ = _session_with_worktree(app, client, repo)
    monkeypatch.setattr(
        "quodeq.api.assistant_workspace_routes.discard_workspace",
        lambda *a, **k: DiscardOutcome("gone"),
    )
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "NO_ACTIVE_WORKTREE"


def test_pr_not_active_has_conflict_code(app, client, repo):
    sid, _, _ = _session_with_worktree(app, client, repo)
    assert client.post(f"/api/assistant/sessions/{sid}/workspace/apply").status_code == 200
    resp = client.post(
        f"/api/assistant/sessions/{sid}/workspace/pr", json={"title": "t", "body": "b"})
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "WORKTREE_CONFLICT"


def test_discard_not_active_has_conflict_code(app, client, repo):
    sid, _, _ = _session_with_worktree(app, client, repo)
    assert client.post(f"/api/assistant/sessions/{sid}/workspace/apply").status_code == 200
    resp = client.post(f"/api/assistant/sessions/{sid}/workspace/discard")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "WORKTREE_CONFLICT"
