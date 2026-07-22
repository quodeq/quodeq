"""Integration locks: assistant sessions with source="shared" target the real
shared-repo clone end to end -- session creation, tool-context construction,
tool dispatch (get_scores/search_findings), and the read-only registry.

Reuses the fake-clone recipe (bare origin + publish_project +
sync_shared_index) via ``shared_clone_fixture``, moved to
tests/api/conftest.py in Task 6 Step 0 so it isn't duplicated here.
"""
from __future__ import annotations

import pytest

from pathlib import Path

from quodeq.api._assistant_helpers import build_tool_context, get_repository
from quodeq.api.app import create_app
from quodeq.assistant.tools import build_registry
from quodeq.services.score_cache import get_score_cache_path, score_cache_path_override
from quodeq.services.shared_repo import shared_evaluations_root, shared_score_cache_path


@pytest.fixture()
def app(tmp_path):
    # create_app only defaults ASSISTANT_DB_PATH when absent from
    # test_config -- to the developer's REAL ~/.quodeq/assistant.db (see
    # api/app.py). This suite POSTs to /api/assistant/sessions, so without
    # an explicit override those calls write real rows into (and migrate)
    # the developer's actual assistant store. Always pin it to an isolated
    # tmp path; see test_app_fixture_isolates_assistant_db below for the
    # regression lock.
    return create_app(test_config={
        "TESTING": True,
        "ASSISTANT_DB_PATH": str(tmp_path / "assistant.db"),
    })


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


def test_app_fixture_isolates_assistant_db(app, tmp_path):
    # create_app defaults ASSISTANT_DB_PATH to the developer's real
    # ~/.quodeq/assistant.db; tests must always override it. `app` and this
    # test both request the (function-scoped) `tmp_path` fixture within the
    # same test node, so pytest hands them the identical directory -- the
    # `app` fixture's override is provably rooted under this test's own
    # `tmp_path`, not just "somewhere outside home".
    assert Path(app.config["ASSISTANT_DB_PATH"]).is_relative_to(tmp_path)


def _create_shared_session(client, run_id=None):
    payload = {"provider": "ollama", "source": "shared", "projectId": "proj-a"}
    if run_id:
        payload["runId"] = run_id
    # create_app (unlike the bare-Flask app fixture in test_assistant_routes.py)
    # wires the real security middleware, which 403s any state-changing
    # request without an Origin header (see security.py::_check_csrf) --
    # same Origin-header requirement other create_app-backed POST tests in
    # this directory already work around (e.g. test_browse_mkdir.py,
    # test_action_api.py).
    resp = client.post("/api/assistant/sessions", json=payload,
                       headers={"Origin": "http://localhost"})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_shared_session_resolves_clone_run_dir(client, app, shared_clone_fixture):
    body = _create_shared_session(client, run_id="run-1")
    row = get_repository(app).get_session(body["sessionId"])
    assert row["source"] == "shared"
    expected_root = str(shared_evaluations_root(shared_clone_fixture))
    assert row["run_id"].startswith(expected_root)
    assert row["project_uuid"] is None  # never a repo root for shared


def test_shared_tool_context_targets_clone(client, app, shared_clone_fixture):
    body = _create_shared_session(client)
    with app.app_context():
        ctx = build_tool_context(app, get_repository(app).get_session(body["sessionId"]))
    assert ctx.read_only is True
    assert ctx.reports_dir == shared_evaluations_root(shared_clone_fixture)
    assert ctx.score_cache_path == shared_score_cache_path(shared_clone_fixture)


def test_shared_get_scores_matches_shared_route(client, app, shared_clone_fixture):
    body = _create_shared_session(client)
    with app.app_context():
        ctx = build_tool_context(app, get_repository(app).get_session(body["sessionId"]))
    registry = build_registry(ctx)
    with score_cache_path_override(ctx.score_cache_path):
        tool_result = registry.dispatch("get_scores", {})
    route = client.get(
        "/api/shared/projects/proj-a/scores?refresh=1").get_json()
    assert tool_result.get("ok") is True
    # Shape adaptation (brief's LOCK: dispatch succeeds AND the dimension set
    # equals the shared route's -- only the key paths below were adjusted):
    #   - ToolRegistry.dispatch wraps the handler's return in {"ok", "result"};
    #     it never itself nests a "dimensions" key, so the tool payload is
    #     read from tool_result["result"], not tool_result["dimensions"].
    #   - _get_scores (tools/_read_tools.py) returns a dict KEYED BY dimension
    #     name (`{"Security": {"score": ..., "grade": ..., "fromRun": ...}}`),
    #     not a list of {"dimension": ...} objects -- so the tool's dimension
    #     set is the dict's keys.
    #   - GET /api/shared/projects/<project>/scores (get_project_scores) nests
    #     its dimension list under "accumulated" (`{"accumulated": {"dimensions":
    #     [...]}, "trend": [...], "availableRuns": [...]}`), not at the
    #     response's top level.
    tool_dims = set(tool_result.get("result", {}).keys())
    route_dims = {d.get("dimension") for d in route.get("accumulated", {}).get("dimensions", [])}
    assert tool_dims == route_dims and "Security" in tool_dims
    # Score-cache isolation: rescoring under the override hits the per-clone
    # cache DB, and nothing appears at the local default cache location.
    assert shared_score_cache_path(shared_clone_fixture).exists()
    assert not Path(get_score_cache_path()).exists()


def test_shared_search_findings_builds_projection_in_clone(client, app, shared_clone_fixture):
    body = _create_shared_session(client, run_id="run-1")
    with app.app_context():
        ctx = build_tool_context(app, get_repository(app).get_session(body["sessionId"]))
    registry = build_registry(ctx)
    with score_cache_path_override(ctx.score_cache_path):
        result = registry.dispatch("search_findings", {"query": "hash"})
    assert result.get("ok") is True
    assert (ctx.run_dir / "evaluation.db").exists()  # projection built in-clone


def test_shared_registry_has_no_draft_action(client, app, shared_clone_fixture):
    body = _create_shared_session(client)
    with app.app_context():
        ctx = build_tool_context(app, get_repository(app).get_session(body["sessionId"]))
    names = {t["function"]["name"] for t in build_registry(ctx).openai_tools()}
    assert "draft_action" not in names
