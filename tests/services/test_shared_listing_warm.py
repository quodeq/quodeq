"""warm_shared_listing runs the list route's hydration and reports the count."""
from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.services import shared_connect_job, shared_listing
from quodeq.services.shared_connect import ConnectOutcome
from quodeq.services.shared_connect_job import ConnectJobStatus, ConnectState, get_connect_status, start_connect
from quodeq.services.shared_repo import RepoFormat
from quodeq.services.score_cache import open_score_cache

_URL = "https://example.invalid/x.git"


def _fake_hydration(monkeypatch, calls):
    def build(eval_root, *, backfill=True, inline_summaries=False):
        calls.append(("build", eval_root, backfill, inline_summaries))
        return [SimpleNamespace(id="a"), SimpleNamespace(id="b")]

    def meta(url, env=None):
        calls.append(("meta", url))
        return {}
    monkeypatch.setattr(shared_listing.fs_projects, "build_project_list", build)
    monkeypatch.setattr(shared_listing, "published_meta", meta)


def test_warm_runs_the_listing_hydration(tmp_path, monkeypatch):
    calls = []
    _fake_hydration(monkeypatch, calls)
    assert shared_listing.warm_shared_listing(tmp_path, _URL) == 2
    assert calls == [("build", tmp_path, False, True), ("meta", _URL)]


def test_warm_skips_a_missing_root(tmp_path, monkeypatch):
    calls = []
    _fake_hydration(monkeypatch, calls)
    assert shared_listing.warm_shared_listing(tmp_path / "absent", _URL) == 0
    assert calls == []


def test_listing_shares_the_hydration_path(tmp_path, monkeypatch):
    calls = []
    _fake_hydration(monkeypatch, calls)
    monkeypatch.setattr(shared_listing, "last_synced_at", lambda url: None)
    listing = shared_listing.list_shared_projects(
        tmp_path, _URL, refresh=False, refresh_clone=None, sync_index=None,
        serialize=lambda p: {"id": p.id},
    )
    assert [p["id"] for p in listing["projects"]] == ["a", "b"]
    assert calls == [("build", tmp_path, False, True), ("meta", _URL)]


def _active_cache_db() -> Path:
    """The score cache DB file open_score_cache resolves to right now."""
    with open_score_cache() as conn:
        return Path(conn.execute("PRAGMA database_list").fetchone()[2])


@pytest.fixture()
def clone_cache(tmp_path, monkeypatch):
    """Isolate the default cache under tmp and give the clone its own cache path."""
    monkeypatch.setenv("QUODEQ_INDEX_DB_PATH", str(tmp_path / "index.db"))
    shared_db = tmp_path / "shared" / "score_cache.db"
    monkeypatch.setattr(shared_listing, "shared_score_cache_path", lambda url, env=None: shared_db)
    return shared_db


def test_warm_hydrates_into_the_clone_score_cache(tmp_path, monkeypatch, clone_cache):
    seen = []

    def build(eval_root, *, backfill=True, inline_summaries=False):
        seen.append(_active_cache_db())
        return []
    monkeypatch.setattr(shared_listing.fs_projects, "build_project_list", build)
    monkeypatch.setattr(shared_listing, "published_meta", lambda url, env=None: {})
    shared_listing.warm_shared_listing(tmp_path, _URL)
    assert seen == [clone_cache.resolve()]
    assert _active_cache_db() == (tmp_path / "score_cache.db").resolve()  # override restored


def test_connect_job_warm_up_lands_in_the_clone_score_cache(tmp_path, monkeypatch, clone_cache):
    """The job's daemon thread does not inherit a route's override; the warm-up must scope its own."""
    root = tmp_path / "evaluations"
    (root / "a").mkdir(parents=True)
    seen = []

    def build(eval_root, *, backfill=True, inline_summaries=False):
        seen.append(_active_cache_db())
        return [SimpleNamespace(id="a")]
    monkeypatch.setattr(shared_listing.fs_projects, "build_project_list", build)
    monkeypatch.setattr(shared_listing, "published_meta", lambda url, env=None: {})
    monkeypatch.setattr(shared_connect_job, "shared_evaluations_root", lambda url, env=None: root)
    monkeypatch.setattr(
        shared_connect_job, "connect_shared_repo", lambda url, **_: ConnectOutcome(status=RepoFormat.OK, url=url),
    )
    status = ConnectJobStatus()

    def on_thread(fn):
        worker = threading.Thread(target=fn)
        worker.start()
        worker.join()
    start_connect(_URL, status=status, spawn=on_thread)
    assert seen == [clone_cache.resolve()]
    assert get_connect_status(status)["state"] == ConnectState.DONE
