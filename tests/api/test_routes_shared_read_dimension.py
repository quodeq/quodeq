"""Per-project /api/shared mirrors: dimension eval, violations and dismissed/verified findings."""
from __future__ import annotations

from quodeq.core.observability import NULL_LOG
from quodeq.services import fs_reports
from quodeq.shared.log_sink import SHARED_LOG
from tests.api._routes_shared_read_fixtures import app, client  # noqa: F401 -- pytest fixtures


# --- GET /api/shared/projects/<project>/dimensions/<dim>/eval -----------------

def test_shared_dimension_eval(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/dimensions/Security/eval?run=run-1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("dimension") == "Security"


def test_shared_dimension_eval_waiting_when_no_eval_file(client, shared_clone_fixture):
    """No evaluation/DoesNotExist.json (or evidence fallback) exists, but the
    run directory does -- same as the local route, this is "waiting" (202),
    not 404. 404 is reserved for a run directory that doesn't exist at all."""
    resp = client.get("/api/shared/projects/proj-a/dimensions/DoesNotExist/eval?run=run-1")
    assert resp.status_code == 202


def test_shared_dimension_eval_not_found_when_run_missing(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/dimensions/Security/eval?run=nonexistent-run")
    assert resp.status_code == 404


def test_shared_dimension_eval_invalid_run_segment(client, shared_clone_fixture):
    """The run comes from a query param here (not a URL path segment), so it
    must still be validated against path traversal before touching disk."""
    resp = client.get("/api/shared/projects/proj-a/dimensions/Security/eval?run=..%2fescape")
    assert resp.status_code == 400


def test_shared_dimension_eval_passes_app_evaluators_dir(app, client, shared_clone_fixture, monkeypatch):
    """The route resolves evaluators_dir from the app's own config (CLEA-DEP-07,
    row 10718) instead of get_dimension_eval reading global config itself."""
    from pathlib import Path

    calls: list[object] = []
    original = fs_reports.get_dimension_eval

    def spy(*args, **kwargs):
        calls.append(kwargs.get("evaluators_dir"))
        return original(*args, **kwargs)

    monkeypatch.setattr(fs_reports, "get_dimension_eval", spy)
    resp = client.get("/api/shared/projects/proj-a/dimensions/Security/eval?run=run-1")
    assert resp.status_code == 200
    assert calls == [Path(app.config["STANDARDS_EVALUATORS_DIR"])]


# --- GET /api/shared/projects/<project>/violations ----------------------------

def test_shared_violations(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/violations?run=run-1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "total" in body
    assert "files" in body


def test_shared_violations_invalid_run_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/violations?run=..%2fescape")
    assert resp.status_code == 400


def test_shared_violations_passes_shared_log_sink(client, shared_clone_fixture, monkeypatch):
    """shared_violations threads log=SHARED_LOG, matching shared_dashboard."""
    calls: list[object] = []
    original = fs_reports.get_violations

    def spy(reports_dir, project, run_id, *, log=NULL_LOG):
        calls.append(log)
        return original(reports_dir, project, run_id, log=log)

    monkeypatch.setattr(fs_reports, "get_violations", spy)
    resp = client.get("/api/shared/projects/proj-a/violations?run=run-1")
    assert resp.status_code == 200
    assert calls == [SHARED_LOG]


# --- GET /api/shared/projects/<project>/findings/dismissed & /verified --------

def test_shared_dismissed_findings_empty(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/findings/dismissed")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_shared_verified_findings_empty(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/findings/verified")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_shared_dismissed_findings_rejects_a_malformed_limit(client, shared_clone_fixture):
    """Final-review item 10: the mirrors follow the same paging rule as the
    local lists instead of silently defaulting a malformed value."""
    resp = client.get("/api/shared/projects/proj-a/findings/dismissed?limit=abc")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert "limit" in body["error"]


def test_shared_verified_findings_rejects_a_malformed_limit(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/findings/verified?limit=abc")
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_INPUT"
    assert "limit" in body["error"]


def test_shared_dismissed_findings_invalid_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/%2e%2e/findings/dismissed")
    assert resp.status_code == 400
