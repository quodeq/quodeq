"""The shared listing reports pending cards and warms them in the background.

Regression context: the shared list computed every project-card summary
inline inside the one list request (the clone had no warm-up engine), and
the connect and refresh jobs ran that same hydration before reporting DONE,
so after a connect or an upgrade no shared project appeared until the last
one was scored. The listing now reports a cold card as pending and queues it
on a warm-up engine scoped to the clone's own score cache, the same contract
the local Repositories list has.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from quodeq.services import shared_connect_job, shared_listing
from quodeq.services.shared_connect import ConnectOutcome
from quodeq.services.shared_connect_job import ConnectJobStatus, ConnectState, get_connect_status, start_connect
from quodeq.services.shared_listing import SharedWarmup
from quodeq.services.shared_repo import RepoFormat
from quodeq.services.score_cache import open_score_cache

_URL = "https://example.invalid/x.git"
_OTHER_URL = "https://example.invalid/y.git"


def _entry(pid: str, pending: bool) -> SimpleNamespace:
    return SimpleNamespace(id=pid, summary_pending=pending)


def _fake_hydration(monkeypatch, calls, entries=None):
    def build(eval_root, *, backfill=True, inline_summaries=False):
        calls.append(("build", eval_root, backfill, inline_summaries))
        return list(entries) if entries is not None else [_entry("a", False), _entry("b", False)]

    def meta(url, env=None):
        calls.append(("meta", url))
        return {}
    monkeypatch.setattr(shared_listing.fs_projects, "build_project_list", build)
    monkeypatch.setattr(shared_listing, "published_meta", meta)


@pytest.fixture(autouse=True)
def fresh_shared_warmup(monkeypatch):
    """Every test gets its own module-level shared warm-up and stops its worker afterwards."""
    warmup = SharedWarmup()
    monkeypatch.setattr(shared_listing, "shared_warmup", warmup)
    yield warmup
    warmup.reset_for_tests()


def _wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return False


def test_warm_counts_the_projects_without_hydrating_inline(tmp_path, monkeypatch):
    calls = []
    _fake_hydration(monkeypatch, calls)
    assert shared_listing.warm_shared_listing(tmp_path, _URL) == 2
    assert calls == [("build", tmp_path, False, False), ("meta", _URL)]


def test_warm_skips_a_missing_root(tmp_path, monkeypatch):
    calls = []
    _fake_hydration(monkeypatch, calls)
    assert shared_listing.warm_shared_listing(tmp_path / "absent", _URL) == 0
    assert calls == []


def test_listing_reports_pending_cards_instead_of_computing_them(tmp_path, monkeypatch):
    calls = []
    _fake_hydration(monkeypatch, calls)
    monkeypatch.setattr(shared_listing, "last_synced_at", lambda url: None)
    listing = shared_listing.list_shared_projects(
        tmp_path, _URL, refresh=False, refresh_clone=None, sync_index=None,
        serialize=lambda p: {"id": p.id, "summaryPending": p.summary_pending},
    )
    assert [p["id"] for p in listing["projects"]] == ["a", "b"]
    assert calls == [("build", tmp_path, False, False), ("meta", _URL)]


def test_listing_queues_the_pending_cards_on_the_shared_warmup(tmp_path, monkeypatch, fresh_shared_warmup):
    warmed: list[tuple[str, str]] = []
    monkeypatch.setattr(shared_listing, "warm_project", lambda reports_dir, pid: warmed.append((reports_dir, pid)))
    _fake_hydration(monkeypatch, [], entries=[_entry("cold", True), _entry("warm", False)])
    monkeypatch.setattr(shared_listing, "last_synced_at", lambda url: None)

    listing = shared_listing.list_shared_projects(
        tmp_path, _URL, refresh=False, refresh_clone=None, sync_index=None, serialize=lambda p: {"id": p.id},
    )

    assert listing["warmup"]["projectsTotal"] >= 1
    assert _wait_until(lambda: warmed == [(str(tmp_path), "cold")])
    assert _wait_until(lambda: fresh_shared_warmup.snapshot()["active"] is False)


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


def test_the_shared_worker_warms_under_the_clone_score_cache(tmp_path, monkeypatch, clone_cache, fresh_shared_warmup):
    seen: list[Path] = []
    monkeypatch.setattr(shared_listing, "warm_project", lambda reports_dir, pid: seen.append(_active_cache_db()))
    _fake_hydration(monkeypatch, [], entries=[_entry("a", True)])

    shared_listing.warm_shared_listing(tmp_path, _URL)

    assert _wait_until(lambda: seen == [clone_cache.resolve()])
    assert _active_cache_db() == (tmp_path / "score_cache.db").resolve()  # the caller's cache is untouched


def test_a_new_url_gets_its_own_engine(tmp_path, monkeypatch, fresh_shared_warmup):
    warmed: list[tuple[str, str]] = []
    monkeypatch.setattr(shared_listing, "warm_project", lambda reports_dir, pid: warmed.append((reports_dir, pid)))
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _fake_hydration(monkeypatch, [], entries=[_entry("a", True)])

    shared_listing.warm_shared_listing(first, _URL)
    assert _wait_until(lambda: warmed == [(str(first), "a")])
    shared_listing.warm_shared_listing(second, _OTHER_URL)
    assert _wait_until(lambda: warmed == [(str(first), "a"), (str(second), "a")])


def test_connect_job_queues_the_clone_for_the_shared_warmup(tmp_path, monkeypatch, clone_cache, fresh_shared_warmup):
    """The job reports DONE as soon as the clone is read; the worker warms under the clone's cache."""
    root = tmp_path / "evaluations"
    (root / "a").mkdir(parents=True)
    seen: list[Path] = []
    monkeypatch.setattr(shared_listing, "warm_project", lambda reports_dir, pid: seen.append(_active_cache_db()))
    _fake_hydration(monkeypatch, [], entries=[_entry("a", True)])
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

    assert get_connect_status(status)["state"] == ConnectState.DONE
    assert _wait_until(lambda: seen == [clone_cache.resolve()])
