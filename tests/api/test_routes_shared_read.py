"""Read-only mirrors of project read endpoints under /api/shared/*.

Read-only invariant: every route under /api/shared/projects/... is a thin GET
delegation to the same service functions the local /api/projects/... routes
use, pointed at the shared clone's evaluations root instead of the local
reports directory. This module covers the ``_with_shared_root`` decorator's
failure branches, the read-only route sweep and GET /api/shared/projects;
the per-project mirror routes live in the test_routes_shared_read_* siblings,
all built against a REAL published clone (tests/api/conftest.py).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quodeq.data.fs.shared_repo import (
    FORMAT_NAME,
    MARKER_FILENAME,
    shared_evaluations_root,
    shared_repo_path,
)
from quodeq.services.shared_settings import SharedSettings, write_settings
from tests.api._routes_shared_read_fixtures import (  # noqa: F401 -- pytest fixtures
    app,
    client,
    empty_shared_clone_fixture,
)


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
    """A foreign repo (real content, no quodeq.json marker) must
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
    assert body["error"] == (
        "the configured repository does not look like a quodeq results repository"
        " — reconnect it in Settings"
    )
    assert body["code"] == "FOREIGN_REPO"


def test_empty_repo_lists_zero_projects_not_503(client, empty_shared_clone_fixture):
    """First connect to an empty (never-published) repo must be
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
    from quodeq.data.fs.shared_repo import shared_score_cache_path
    from quodeq.shared.env import get_score_cache_path

    clone_cache_path = shared_score_cache_path(shared_clone_fixture)
    local_cache_path = Path(get_score_cache_path())
    assert not clone_cache_path.exists()
    assert not local_cache_path.exists()

    resp = client.get("/api/shared/projects")
    assert resp.status_code == 200

    assert clone_cache_path.exists()
    assert not local_cache_path.exists()


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
