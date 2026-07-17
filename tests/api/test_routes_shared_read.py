"""Tests for the read-only mirrors of project read endpoints under /api/shared/*.

Read-only invariant: every route under /api/shared/projects/... is a thin GET
delegation to the same service functions the local /api/projects/... routes
use, pointed at the shared clone's evaluations root instead of the local
reports directory. This module covers:

  * the ``_with_shared_root`` decorator's three failure branches (409
    unconfigured, 409 unsupported clone format, 503 clone not cloned yet)
  * the durable read-only sweep test (no mutating routes under /api/shared
    beyond the three already-established control endpoints)
  * one smoke test per mirror route, built against a REAL published clone
    (bare origin + publish_project + sync_shared_index, same recipe as
    tests/services/test_shared_repo.py) driven through the Flask test client
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.core.events.models import JudgmentCreatedEvent, JudgmentPayload
from quodeq.core.events.writer import EventLogWriter
from quodeq.services.shared_publish import publish_project
from quodeq.services.shared_repo import (
    FORMAT_NAME,
    MARKER_FILENAME,
    shared_evaluations_root,
    shared_repo_path,
    sync_shared_index,
)
from quodeq.services.shared_settings import SharedSettings, write_settings

_VIOLATION = dict(
    practice_id="P1", verdict="violation", dimension="Security",
    file="a.py", line=10, reason="weak hash", req="R1", severity="high",
)

_EVAL_JSON = {
    "schema_version": 1,
    "dimension": "Security",
    "project": "proj-a",
    "runId": "run-1",
    "overallScore": "7.0/10",
    "overallGrade": "Good",
    "principles": [{"name": "Integrity", "score": "7.0/10", "grade": "Good", "violations": [], "compliance": []}],
    "violations": [{
        "principle": "Integrity", "req": "R1", "file": "a.py", "line": 10,
        "severity": "major", "reason": "bad", "title": "Bad",
    }],
    "compliance": [],
}


def _make_origin(tmp_path: Path) -> str:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    return f"file://{origin}"


@pytest.fixture()
def app():
    return create_app(test_config={"TESTING": True})


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def shared_clone_fixture(tmp_path, monkeypatch):
    """Build a real published shared-repo clone and point settings at it.

    Follows the same recipe as
    tests/services/test_shared_repo.py::test_readable_and_index_sync_on_published_clone:
    bare origin + publish_project + sync_shared_index. ``publish_project``'s
    staging allowlist (source-of-truth files only) never carries
    ``evaluation/<dim>.json`` — a real published run always has that
    directory empty — so a per-dimension eval file is written directly into
    the clone afterwards to exercise the dashboard/accumulated/dimension-eval/
    violations read paths (this task's job) against real content, without
    relitigating the publish allowlist (a prior task's decision).
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "tester")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "tester")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")

    url = _make_origin(tmp_path)
    local_root = tmp_path / "local-evaluations"
    project_dir = local_root / "proj-a"
    run_dir = project_dir / "run-1"
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}", encoding="utf-8")
    (project_dir / "repository_info.json").write_text(
        json.dumps({"name": "proj-a"}), encoding="utf-8",
    )
    (run_dir / "status.json").write_text(
        json.dumps({"state": "done", "schema_version": 2}), encoding="utf-8",
    )
    (run_dir / "dimensions.json").write_text("{}", encoding="utf-8")

    writer = EventLogWriter(run_dir / "events.jsonl")
    writer.emit(JudgmentCreatedEvent(payload=JudgmentPayload(**_VIOLATION)))

    publish_project("proj-a", url, evaluations_root=local_root)
    sync_shared_index(url)

    repo_run_dir = shared_evaluations_root(url) / "proj-a" / "run-1"
    (repo_run_dir / "evaluation").mkdir(parents=True, exist_ok=True)
    (repo_run_dir / "evaluation" / "Security.json").write_text(
        json.dumps(_EVAL_JSON), encoding="utf-8",
    )

    write_settings(SharedSettings(url=url))
    return url


# --- _with_shared_root decorator ---------------------------------------------

def test_shared_routes_409_when_unconfigured(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    for path in (
        "/api/shared/projects",
        "/api/shared/projects/x/runs",
        "/api/shared/projects/x/dashboard",
    ):
        resp = client.get(path)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "no shared repository configured"


def test_shared_routes_503_when_clone_missing(client):
    write_settings(SharedSettings(url="file:///nonexistent/repo.git"))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "shared repository has not been cloned yet"


def test_shared_routes_409_when_unsupported_version(client):
    url = "file:///dummy/unsupported.git"
    repo = shared_repo_path(url)
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / MARKER_FILENAME).write_text(
        json.dumps({"format": FORMAT_NAME, "version": 99}), encoding="utf-8",
    )
    write_settings(SharedSettings(url=url))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 409
    assert "newer version" in resp.get_json()["error"]


# --- read-only sweep ----------------------------------------------------------

def test_no_mutating_routes_under_shared(app):
    """Read-only invariant: /api/shared/* accepts only GET plus the four control POST/PUT/DELETE."""
    allowed_mutations = {
        ("/api/shared/config", "PUT"),
        ("/api/shared/config", "DELETE"),
        ("/api/shared/refresh", "POST"),
        # Deliberate, spec-approved exception: this mutates LOCAL state (the
        # local reports directory, via import_zip_stream) to materialize a
        # copy of a shared project -- it does not mutate the shared
        # repository clone itself, so it does not violate the read-only
        # invariant this test enforces for the shared repo.
        ("/api/shared/projects/<project>/pull", "POST"),
    }
    for rule in app.url_map.iter_rules():
        if not str(rule).startswith("/api/shared"):
            continue
        for method in rule.methods - {"HEAD", "OPTIONS", "GET"}:
            assert (str(rule), method) in allowed_mutations, f"unexpected {method} {rule}"


# --- GET /api/shared/projects -------------------------------------------------

def test_shared_projects_lists_published(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200
    body = resp.get_json()
    ids = [p.get("id") or p.get("name") for p in body["projects"]]
    assert "proj-a" in ids
    proj = next(p for p in body["projects"] if (p.get("id") or p.get("name")) == "proj-a")
    assert proj.get("publishedBy") == "tester"
    assert proj.get("source") == "shared"
    assert "lastSynced" in body


def test_shared_projects_without_refresh_param_omits_stale(client, shared_clone_fixture):
    """Backward compat: a plain GET (no ?refresh=1) never forces a fetch and
    never gains a "stale" key -- the refresh-on-read behaviour is opt-in."""
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200
    assert "stale" not in resp.get_json()


def test_shared_projects_refresh_success_reports_fresh_and_syncs_index(
    client, shared_clone_fixture, monkeypatch
):
    """?refresh=1 calls refresh_shared_clone first; on success it also calls
    sync_shared_index and the response gains "stale": False."""
    calls: list[str] = []
    monkeypatch.setattr(
        "quodeq.api.routes_shared.refresh_shared_clone",
        lambda url: calls.append(f"refresh:{url}") or True,
    )
    monkeypatch.setattr(
        "quodeq.api.routes_shared.sync_shared_index",
        lambda url: calls.append(f"sync:{url}"),
    )
    resp = client.get("/api/shared/projects?refresh=1")
    assert resp.status_code == 200
    assert resp.get_json()["stale"] is False
    assert calls == [f"refresh:{shared_clone_fixture}", f"sync:{shared_clone_fixture}"]


def test_shared_projects_refresh_failure_reports_stale_and_skips_sync(
    client, shared_clone_fixture, monkeypatch
):
    """When refresh_shared_clone fails, the response gains "stale": True and
    sync_shared_index is never called (nothing new was fetched to index)."""
    sync_calls: list[str] = []
    monkeypatch.setattr("quodeq.api.routes_shared.refresh_shared_clone", lambda url: False)
    monkeypatch.setattr(
        "quodeq.api.routes_shared.sync_shared_index",
        lambda url: sync_calls.append(url),
    )
    resp = client.get("/api/shared/projects?refresh=1")
    assert resp.status_code == 200
    assert resp.get_json()["stale"] is True
    assert sync_calls == []


def test_shared_projects_refresh_stale_when_origin_unreachable(
    client, shared_clone_fixture, tmp_path
):
    """End-to-end: the origin bare repo becomes unreachable (e.g. renamed
    away/deleted), so `git fetch` fails and the forced refresh reports
    stale, while the already-cloned (now-stale) project listing still
    renders from the local cache instead of erroring out."""
    origin_path = Path(shared_clone_fixture.removeprefix("file://"))
    origin_path.rename(tmp_path / "origin-moved.git")

    resp = client.get("/api/shared/projects?refresh=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["stale"] is True
    ids = [p.get("id") or p.get("name") for p in body["projects"]]
    assert "proj-a" in ids


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
    from quodeq.services.shared_repo import shared_score_cache_path

    cache_path = shared_score_cache_path(shared_clone_fixture)
    assert not cache_path.exists()
    resp = client.get("/api/shared/projects/proj-a/scores")
    assert resp.status_code == 200
    assert cache_path.exists()


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


# --- GET /api/shared/projects/<project>/findings/dismissed & /verified --------

def test_shared_dismissed_findings_empty(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/findings/dismissed")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_shared_verified_findings_empty(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/proj-a/findings/verified")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_shared_dismissed_findings_invalid_segment(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects/%2e%2e/findings/dismissed")
    assert resp.status_code == 400
