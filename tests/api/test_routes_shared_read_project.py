"""Per-project /api/shared mirrors: info, runs, dashboard, accumulated, scores, compare-summary and the fleet compare."""
from __future__ import annotations

from quodeq.services.scoring.compliance_detail import DETAIL_FIELDS
from tests.api._routes_shared_read_fixtures import (  # noqa: F401 -- pytest fixtures
    app,
    client,
    get_shared_settled,
    wait_shared_warmup_idle,
)


# --- GET /api/shared/projects/<project>/info ----------------------------------

def test_shared_project_info(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/info")
    assert resp.status_code == 200
    body = resp.get_json()
    # Pins services/shared_listing.py's enrich_shared_info publishedBy/source
    # merge so it stays byte-identical to the list route's per-project merge.
    assert body.get("publishedBy") == "tester"
    assert body.get("source") == "shared"


def test_shared_project_info_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/does-not-exist/info")
    assert resp.status_code == 404


def test_shared_project_info_invalid_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/%2e%2e/info")
    assert resp.status_code == 400


def test_shared_project_info_returns_sanitized_500_on_a_read_failure(
    client, shared_clone_fixture, monkeypatch,
):
    """shared_project_info is reached via a publicly shared URL,
    unlike most of this app's local-only UI. An OSError/sqlite3.Error/
    ValueError from get_project_info (a read failure the route expects) must
    still degrade to the sanitized {"error", "code"} contract its siblings
    (shared_runs, shared_scores, shared_compare_summary) return, with the
    raised exception's own text never reaching the response body."""
    import quodeq.services.fs_projects as fs_projects_mod

    secret_detail = "SECRET_DB_PATH=/private/leak/db.sqlite exploded"

    def _boom(*_args, **_kwargs):
        raise OSError(secret_detail)

    monkeypatch.setattr(fs_projects_mod, "get_project_info", _boom)

    resp = client.get("/api/shared/projects/proj-a/info")

    assert resp.status_code == 500
    body = resp.get_json()
    assert body is not None, "Response body must be JSON, not a raw Flask error page"
    assert body == {"error": "Failed to load project info", "code": "INTERNAL_ERROR"}

    raw = resp.get_data(as_text=True)
    assert secret_detail not in raw
    assert "OSError" not in raw
    assert "Traceback" not in raw


def test_shared_project_info_propagates_an_error_outside_the_narrowed_tuple(
    client, shared_clone_fixture, monkeypatch,
):
    """A RuntimeError (not OSError/sqlite3.Error/ValueError) is a real bug in
    get_project_info, not a read failure, so the route's own narrow tuple
    does not catch it, and it is not wrapped into the route's own sanitized
    JSON 500. It still escapes the route -- the app-wide fallback handler
    (api/_error_handlers.py) is what turns it into a generic coded 500
    instead of Flask's default HTML page."""
    import quodeq.services.fs_projects as fs_projects_mod

    def _boom(*_args, **_kwargs):
        raise RuntimeError("unexpected bug")

    monkeypatch.setattr(fs_projects_mod, "get_project_info", _boom)

    resp = client.get("/api/shared/projects/proj-a/info")

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["code"] == "INTERNAL_ERROR"
    assert "unexpected bug" not in resp.get_data(as_text=True)


# --- GET /api/shared/projects/<project>/runs ----------------------------------

def test_shared_runs(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/runs")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "runs" in body
    run_ids = [r.get("runId") for r in body["runs"]]
    assert "run-1" in run_ids


# --- GET /api/shared/projects/<project>/dashboard -----------------------------

def test_shared_dashboard(client, shared_clone_fixture):
    resp = get_shared_settled(client, "/api/shared/projects/proj-a/dashboard")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("project") == "proj-a"
    dims = body.get("dimensions", [])
    assert any(d.get("dimension") == "Security" for d in dims)


def test_shared_dashboard_with_run_param(client, shared_clone_fixture):
    resp = get_shared_settled(client, "/api/shared/projects/proj-a/dashboard?run=run-1")
    assert resp.status_code == 200


def test_shared_dashboard_invalid_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/%2e%2e/dashboard")
    assert resp.status_code == 400


# --- GET /api/shared/projects/<project>/accumulated ---------------------------

def test_shared_accumulated(client, shared_clone_fixture):
    resp = get_shared_settled(client, "/api/shared/projects/proj-a/accumulated")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "dimensions" in body


def test_shared_accumulated_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/does-not-exist/accumulated")
    assert resp.status_code == 404


# --- GET /api/shared/projects/<project>/scores --------------------------------

def test_shared_scores(client, shared_clone_fixture):
    # A cold shared project answers pending while the clone's worker warms
    # it (never built inline on the request), then serves the payload.
    resp = client.get("/api/shared/projects/proj-a/scores")
    assert resp.status_code == 202
    assert resp.get_json()["pending"] is True
    wait_shared_warmup_idle()
    resp = client.get("/api/shared/projects/proj-a/scores")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "accumulated" in body
    assert "trend" in body
    assert "availableRuns" in body


def test_shared_scores_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/does-not-exist/scores")
    assert resp.status_code == 404


def test_shared_scores_uses_isolated_score_cache(client, shared_clone_fixture):
    """The shared clone's own score_cache.db is touched,
    not the local (unconfigured, in this test) default score cache path."""
    from quodeq.data.fs.shared_repo import shared_score_cache_path

    cache_path = shared_score_cache_path(shared_clone_fixture)
    assert not cache_path.exists()
    resp = client.get("/api/shared/projects/proj-a/scores")
    assert resp.status_code == 202
    wait_shared_warmup_idle()
    assert cache_path.exists()
    assert client.get("/api/shared/projects/proj-a/scores").status_code == 200


# --- GET /api/shared/projects/<project>/compare-summary -----------------------

def test_shared_compare_summary(client, shared_clone_fixture):
    """The Compare tab's slim payload served from the shared clone's own
    evaluations root: same shape as the local endpoint, findings stripped."""
    resp = client.get("/api/shared/projects/proj-a/compare-summary")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["project"] == "proj-a"
    assert "summary" in body
    assert "trend" in body
    assert isinstance(body["dimensions"], list)
    for dim in body["dimensions"]:
        assert "violations" not in dim
        assert "compliance" not in dim
    # The clone records the publisher's repo path, which does not exist
    # here — the staleness signal must fail open, not error.
    assert body["commitsSinceLastRun"] is None or isinstance(body["commitsSinceLastRun"], int)


def test_shared_compare_summary_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/does-not-exist/compare-summary")
    assert resp.status_code == 404


def test_shared_compare_summary_unconfigured_409(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.get("/api/shared/projects/proj-a/compare-summary")
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "no shared repository configured"


# --- GET /api/shared/fleet/compare --------------------------------------------

def test_shared_fleet_compare(client, shared_clone_fixture):
    """Every listed shared project in one response; unknown names land in errors."""
    resp = client.get("/api/shared/fleet/compare?projects=proj-a,does-not-exist")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [s["project"] for s in body["summaries"]] == ["proj-a"]
    assert body["errors"] == {"does-not-exist": "Project not found"}
    for dim in body["summaries"][0]["dimensions"]:
        assert "violations" not in dim


def test_shared_fleet_compare_requires_projects(client, shared_clone_fixture):
    assert client.get("/api/shared/fleet/compare").status_code == 400
    assert client.get("/api/shared/fleet/compare?projects=proj-a,%2e%2e").status_code == 400


def test_shared_fleet_compare_unconfigured_409(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    assert client.get("/api/shared/fleet/compare?projects=proj-a").status_code == 409


# --- GET /api/shared/projects/<project>/scores/<run_id> -----------------------

def test_shared_run_scores(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/scores/run-1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "dimensions" in body
    # Same deferred shape as the local /scores/<run>: identity and scalar
    # fields stay, bodies are refilled by /compliance-detail?run=.
    items = [v for dim in body["dimensions"] for v in dim.get("violations", [])]
    assert items
    for v in items:
        assert v["detailDeferred"] is True
        assert not DETAIL_FIELDS & set(v)
        assert {"req", "file", "line"} <= set(v)


def test_shared_compliance_detail_refills_a_runs_deferred_detail(client, shared_clone_fixture):
    run = client.get("/api/shared/projects/proj-a/scores/run-1").get_json()
    dim = next(d for d in run["dimensions"] if d.get("violations"))
    resp = client.get(
        f"/api/shared/projects/proj-a/compliance-detail?dimension={dim['dimension']}&kind=violation&run=run-1")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == len(dim["violations"])
    assert all("detailDeferred" not in item for item in items)
    assert client.get(
        f"/api/shared/projects/proj-a/compliance-detail?dimension={dim['dimension']}&kind=violation&run=nope",
    ).status_code == 404


def test_shared_run_scores_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/scores/nonexistent-run")
    assert resp.status_code == 404
