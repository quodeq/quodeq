"""Per-project /api/shared mirrors: info, runs, dashboard, accumulated, scores and compare-summary."""
from __future__ import annotations

from tests.api._routes_shared_read_fixtures import app, client  # noqa: F401 -- pytest fixtures


# --- GET /api/shared/projects/<project>/info ----------------------------------

def test_shared_project_info(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/info")
    assert resp.status_code == 200


def test_shared_project_info_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/does-not-exist/info")
    assert resp.status_code == 404


def test_shared_project_info_invalid_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/%2e%2e/info")
    assert resp.status_code == 400


def test_shared_project_info_returns_sanitized_500_on_unexpected_error(
    client, shared_clone_fixture, monkeypatch,
):
    """Cluster 11: shared_project_info is reached via a publicly shared URL,
    unlike most of this app's local-only UI. Before this fix it had no
    try/except at all -- an unexpected exception from get_project_info would
    propagate straight into Flask's raw error handling instead of the
    sanitized {"error", "code"} contract its three siblings (shared_runs,
    shared_scores, shared_compare_summary) already return. This locks the
    same contract in for shared_project_info and confirms the raised
    exception's own text never reaches the response body."""
    import quodeq.services._fs_projects as fs_projects_mod

    secret_detail = "SECRET_DB_PATH=/private/leak/db.sqlite exploded"

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(fs_projects_mod, "get_project_info", _boom)

    resp = client.get("/api/shared/projects/proj-a/info")

    assert resp.status_code == 500
    body = resp.get_json()
    assert body is not None, "Response body must be JSON, not a raw Flask error page"
    assert body == {"error": "Failed to load project info", "code": "INTERNAL_ERROR"}

    raw = resp.get_data(as_text=True)
    assert secret_detail not in raw
    assert "RuntimeError" not in raw
    assert "Traceback" not in raw


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
    resp = client.get("/api/shared/projects/proj-a/dashboard")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("project") == "proj-a"
    dims = body.get("dimensions", [])
    assert any(d.get("dimension") == "Security" for d in dims)


def test_shared_dashboard_with_run_param(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/dashboard?run=run-1")
    assert resp.status_code == 200


def test_shared_dashboard_invalid_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/%2e%2e/dashboard")
    assert resp.status_code == 400


# --- GET /api/shared/projects/<project>/accumulated ---------------------------

def test_shared_accumulated(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/accumulated")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "dimensions" in body


def test_shared_accumulated_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/does-not-exist/accumulated")
    assert resp.status_code == 404


# --- GET /api/shared/projects/<project>/scores --------------------------------

def test_shared_scores(client, shared_clone_fixture):
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
    """Task 9 integration: the shared clone's own score_cache.db is touched,
    not the local (unconfigured, in this test) default score cache path."""
    from quodeq.data.fs.shared_repo import shared_score_cache_path

    cache_path = shared_score_cache_path(shared_clone_fixture)
    assert not cache_path.exists()
    resp = client.get("/api/shared/projects/proj-a/scores")
    assert resp.status_code == 200
    assert cache_path.exists()


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


# --- GET /api/shared/projects/<project>/scores/<run_id> -----------------------

def test_shared_run_scores(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/scores/run-1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "dimensions" in body
    for dim in body["dimensions"]:
        for v in dim.get("violations", []):
            assert set(v.keys()) == {"req", "file", "line"}


def test_shared_run_scores_not_found(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/scores/nonexistent-run")
    assert resp.status_code == 404
