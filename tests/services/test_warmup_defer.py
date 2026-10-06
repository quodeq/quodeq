"""An Overview request for a project the warm-up still owes is deferred, not computed inline.

Regression context: at boot (or after an upgrade invalidated the score
caches) the Overview of a large project was built inline on the request path
while the warm-up thread was rebuilding the same project beside it. The two
fought for the interpreter, the build outlived the client's timeout, and the
retry started the work a second time. The route now asks the engine first:
when it still owes the project, the project jumps the queue and the client
gets a pending body to poll on.
"""
from __future__ import annotations

import threading

import pytest

from quodeq.services.warmup import WarmupEngine
from quodeq.services.warmup_defer import defer_to_warmup


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


_LISTING = [("a", "2026-08-04"), ("b", "2026-08-03"), ("selected", "2026-08-01")]


def test_owes_is_true_for_the_running_and_queued_projects_only(tmp_path, engines):
    eng, _order, first_started, release, all_done = _blocked_engine(engines, _LISTING)
    eng.start(str(tmp_path))
    assert first_started.wait(5)

    assert eng.owes("a")           # running
    assert eng.owes("selected")    # queued
    assert not eng.owes("never-queued")

    release.set()
    assert all_done.wait(5)
    assert not eng.owes("selected")


def test_defer_is_none_before_the_engine_starts(tmp_path, engines):
    eng = WarmupEngine(warm_fn=lambda *_: None, list_fn=lambda _rd: [])
    engines.append(eng)
    assert defer_to_warmup(str(tmp_path), "p", engine=eng, summary_pending=lambda *_: True) is None


def test_defer_is_none_for_a_project_the_engine_does_not_owe(tmp_path, engines):
    eng, _order, first_started, release, _all_done = _blocked_engine(engines, _LISTING)
    eng.start(str(tmp_path))
    assert first_started.wait(5)
    try:
        assert defer_to_warmup(str(tmp_path), "never-queued", engine=eng, summary_pending=lambda *_: True) is None
    finally:
        release.set()


def test_defer_is_none_when_the_summary_is_already_cached(tmp_path, engines):
    """A queued project whose caches are warm is served inline, not held behind the queue."""
    eng, _order, first_started, release, _all_done = _blocked_engine(engines, _LISTING)
    eng.start(str(tmp_path))
    assert first_started.wait(5)
    probes: list[tuple[str, str]] = []

    def summary_pending(reports_dir, project_id):
        probes.append((reports_dir, project_id))
        return False
    try:
        assert defer_to_warmup(str(tmp_path), "selected", engine=eng, summary_pending=summary_pending) is None
        assert probes == [(str(tmp_path), "selected")]
    finally:
        release.set()


def test_defer_moves_an_owed_cold_project_to_the_front_and_reports_pending(tmp_path, engines):
    eng, order, first_started, release, all_done = _blocked_engine(engines, _LISTING)
    eng.start(str(tmp_path))
    assert first_started.wait(5)

    body = defer_to_warmup(str(tmp_path), "selected", engine=eng, summary_pending=lambda *_: True)

    assert body == {
        "pending": True,
        "warmup": {"active": True, "projectsDone": 0, "projectsTotal": 3, "currentProjectName": "a"},
    }
    release.set()
    assert all_done.wait(5)
    assert order == ["a", "selected", "b"]


def test_the_project_being_warmed_is_deferred_even_when_its_summary_is_cached(tmp_path, engines):
    """The worker fills the summary first and the scores and Overview after, so a cache
    hit on the summary does not mean the project is warm: building inline beside the
    worker is the contention this module exists to avoid."""
    eng, _order, first_started, release, _all_done = _blocked_engine(engines, _LISTING)
    eng.start(str(tmp_path))
    assert first_started.wait(5)
    probes: list[str] = []

    def summary_pending(_reports_dir, project_id):
        probes.append(project_id)
        return False
    try:
        body = defer_to_warmup(str(tmp_path), "a", engine=eng, summary_pending=summary_pending)
        assert body is not None and body["pending"] is True
        assert probes == []
    finally:
        release.set()
