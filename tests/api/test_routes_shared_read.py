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
from quodeq.services.shared_repo import (
    FORMAT_NAME,
    MARKER_FILENAME,
    ensure_shared_clone,
    shared_evaluations_root,
    shared_repo_path,
)
from quodeq.services.shared_settings import SharedSettings, write_settings
from tests.api.conftest import _make_origin

# _VIOLATION, _EVAL_JSON, _make_origin and shared_clone_fixture moved to
# tests/api/conftest.py (Task 6, Step 0) so test_assistant_shared_sessions.py
# can reuse the fake-clone recipe without duplicating it. _make_origin is
# imported back here because empty_shared_clone_fixture (below) still needs
# it and is not itself part of the move.


@pytest.fixture()
def app():
    return create_app(test_config={"TESTING": True})


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def empty_shared_clone_fixture(tmp_path):
    """A cloned-but-never-published shared repo (audit A1's "empty" case).

    The clone exists for real (a real `git clone` of a real local bare
    origin) but nothing has ever been published into it, so read_state
    reports "empty" rather than "missing". Mirrors shared_clone_fixture
    minus the publish_project step.
    """
    url = _make_origin(tmp_path)
    assert ensure_shared_clone(url) is not None
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
    assert resp.get_json()["error"] == (
        "the shared repository has not been cloned yet — reconnect it in Settings"
    )


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


def test_shared_routes_409_when_foreign(client):
    """Audit A1: a foreign repo (real content, no quodeq.json marker) must
    be rejected at read time with a distinct 409, not silently 503'd or
    served as if it were a real quodeq clone."""
    url = "file:///dummy/foreign.git"
    repo = shared_repo_path(url)
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("some other project", encoding="utf-8")
    write_settings(SharedSettings(url=url))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"] == "the configured repository does not look like a quodeq results repository"
    assert body["code"] == "FOREIGN_REPO"


def test_empty_repo_lists_zero_projects_not_503(client, empty_shared_clone_fixture):
    """Audit A1: first connect to an empty (never-published) repo must be
    servable -- an empty projects list, not a false "not cloned yet" 503."""
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200
    assert resp.get_json()["projects"] == []


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
        lambda url: (calls.append(f"refresh:{url}") or True, ""),
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
    monkeypatch.setattr(
        "quodeq.api.routes_shared.refresh_shared_clone", lambda url: (False, "network unreachable")
    )
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


def _git_porcelain(repo: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True,
    ).stdout


def test_shared_projects_listing_does_not_dirty_clone_worktree(client, shared_clone_fixture):
    """Finding 2 regression: build_project_list's lazy onboarding backfill
    writes onboardingCompletedAt into repository_info.json when missing --
    the shared route must skip that write (backfill=False), or listing
    dirties the clone's git worktree and a subsequent publish's
    `pull --rebase` can refuse (offline refresh) with a confusing wedge.

    shared_clone_fixture already publishes a repository_info.json without
    onboardingCompletedAt (just {"name": "proj-a"}), so no extra fixture
    crafting is needed to exercise the missing-field path. The fixture also
    writes an evaluation/Security.json straight into the clone's working
    tree without `git add`ing it (see its docstring), which is pre-existing
    untracked noise unrelated to this bug -- so this test compares the
    worktree's git status BEFORE and AFTER the request instead of asserting
    a blanket-clean tree, to isolate exactly what the route call itself does.
    """
    repo = shared_repo_path(shared_clone_fixture)
    info_path = shared_evaluations_root(shared_clone_fixture) / "proj-a" / "repository_info.json"
    info_before = json.loads(info_path.read_text(encoding="utf-8"))
    assert "onboardingCompletedAt" not in info_before
    status_before = _git_porcelain(repo)

    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200

    status_after = _git_porcelain(repo)
    assert status_after == status_before
    info_after = json.loads(info_path.read_text(encoding="utf-8"))
    assert "onboardingCompletedAt" not in info_after


def test_shared_projects_score_cache_override_propagates_into_pool(
    client, shared_clone_fixture,
):
    """Finding 1 regression: build_project_list runs _build_one (which
    ultimately calls cached_project_summary) inside a ThreadPoolExecutor.
    contextvars do NOT propagate into pool worker threads by default, so the
    score_cache_path_override set by _with_shared_root would be invisible
    there and per-project summaries would read/write the LOCAL score cache
    DB instead of this clone's own one. Both must hold: the per-clone cache
    gets written, and the local (sandboxed-default) cache never does."""
    from quodeq.services.shared_repo import shared_score_cache_path
    from quodeq.shared._env import get_score_cache_path

    clone_cache_path = shared_score_cache_path(shared_clone_fixture)
    local_cache_path = Path(get_score_cache_path())
    assert not clone_cache_path.exists()
    assert not local_cache_path.exists()

    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200

    assert clone_cache_path.exists()
    assert not local_cache_path.exists()


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


def test_shared_projects_expose_origin_url_and_score_fields(client, shared_clone_fixture):
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200
    proj = next(
        p for p in resp.get_json()["projects"]
        if (p.get("id") or p.get("name")) == "proj-a"
    )
    assert proj.get("originUrl") == "https://github.com/example/proj-a.git"
    # Regression lock: shared listings compute scores from the clone-scoped
    # score cache; the merge UI sorts on this field.
    assert "latestScore" in proj
