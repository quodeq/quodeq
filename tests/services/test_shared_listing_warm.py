"""warm_shared_listing runs the list route's hydration and reports the count."""
from __future__ import annotations

from types import SimpleNamespace

from quodeq.services import shared_listing

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
