"""The project on screen is warmed before the rest of the queue."""
from __future__ import annotations

import threading

import pytest

from quodeq.services.warmup import WarmupEngine


@pytest.fixture
def engines():
    created: list[WarmupEngine] = []
    yield created
    for eng in created:
        eng.reset_for_tests()


def _blocked_engine(engines, listing):
    """An engine whose worker holds the first project until *release* is set."""
    order: list[str] = []
    first_started, release, all_done = threading.Event(), threading.Event(), threading.Event()

    def warm(_reports_dir, pid):
        order.append(pid)
        if len(order) == 1:
            first_started.set()
            assert release.wait(5)
        if len(order) == len(listing):
            all_done.set()

    eng = WarmupEngine(warm_fn=warm, list_fn=lambda _rd: listing)
    engines.append(eng)
    return eng, order, first_started, release, all_done


def test_a_queued_project_moves_to_the_front(tmp_path, engines):
    listing = [("a", "2026-08-04"), ("b", "2026-08-03"), ("c", "2026-08-02"), ("selected", "2026-08-01")]
    eng, order, first_started, release, all_done = _blocked_engine(engines, listing)
    eng.start(str(tmp_path))
    assert first_started.wait(5)

    eng.prioritise("selected")
    release.set()

    assert all_done.wait(5)
    assert order == ["a", "selected", "b", "c"]


def test_the_running_project_and_unknown_ids_are_noops(tmp_path, engines):
    listing = [("a", "2026-08-03"), ("b", "2026-08-02"), ("c", "2026-08-01")]
    eng, order, first_started, release, all_done = _blocked_engine(engines, listing)
    eng.start(str(tmp_path))
    assert first_started.wait(5)

    eng.prioritise("a")        # already running
    eng.prioritise("missing")  # never queued
    release.set()

    assert all_done.wait(5)
    assert order == ["a", "b", "c"]


def test_prioritise_before_start_is_a_noop(engines):
    eng = WarmupEngine(warm_fn=lambda *_: None, list_fn=lambda _rd: [])
    engines.append(eng)
    eng.prioritise("anything")
    assert eng.snapshot() is None


def test_the_scores_route_prioritises_its_project(monkeypatch):
    from quodeq.api.app import create_app
    from quodeq.services.warmup import engine

    calls: list[str] = []
    monkeypatch.setattr(engine, "prioritise", calls.append)
    client = create_app().test_client()

    client.get("/api/projects/some-project/scores")

    assert calls == ["some-project"]
