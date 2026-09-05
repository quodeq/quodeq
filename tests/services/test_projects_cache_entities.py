"""ProjectsCache caches entities; the route owns serialization (WS6).

The cache used to store the camelCase wire payload, a declared
serialization-ratchet entry. It now caches ``ProjectEntry`` objects — the
expensive part (the disk walk) stays cached, and the cheap camelCase
mapping happens per request at the route boundary.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.core.types import ProjectEntry
from quodeq.services._projects_cache import ProjectsCache


def _entry(pid: str = "p1") -> ProjectEntry:
    return ProjectEntry(id=pid, name="proj", runs_count=2, latest_run_id="r2")


def test_cache_returns_entities_not_wire_dicts(tmp_path):
    with patch(
        "quodeq.services._projects_cache._fs_projects.build_project_list",
        return_value=[_entry()],
    ):
        out = ProjectsCache().list(str(tmp_path))

    assert out["projects"] == [_entry()]
    assert isinstance(out["projects"][0], ProjectEntry)


def test_cache_still_collapses_repeat_reads(tmp_path):
    with patch(
        "quodeq.services._projects_cache._fs_projects.build_project_list",
        return_value=[_entry()],
    ) as spy:
        cache = ProjectsCache()
        cache.list(str(tmp_path))
        cache.list(str(tmp_path))

    assert spy.call_count == 1, "the TTL window must still collapse the disk walk"


def test_invalidate_forces_a_reread(tmp_path):
    with patch(
        "quodeq.services._projects_cache._fs_projects.build_project_list",
        return_value=[_entry()],
    ) as spy:
        cache = ProjectsCache()
        cache.list(str(tmp_path))
        cache.invalidate()
        cache.list(str(tmp_path))

    assert spy.call_count == 2


def test_concurrent_cold_reads_share_one_build(tmp_path):
    """Requests racing a cold cache must share ONE disk walk.

    Regression (v1.9.0 startup storm): the client re-requests /api/projects
    while the first build is still running; without an in-flight lock every
    request started its own full build_project_list, multiplying minutes of
    post-upgrade recompute by the number of piled-up requests.
    """
    import threading
    import time as _time

    calls = []

    def slow_build(_root):
        calls.append(1)
        _time.sleep(0.05)
        return [_entry()]

    with patch(
        "quodeq.services._projects_cache._fs_projects.build_project_list",
        side_effect=slow_build,
    ):
        cache = ProjectsCache()
        barrier = threading.Barrier(4)
        results = [None] * 4

        def hit(i):
            barrier.wait()
            results[i] = cache.list(str(tmp_path))

        threads = [threading.Thread(target=hit, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(calls) == 1, "concurrent cold reads must collapse into one build"
    assert all(r == results[0] for r in results)


def test_service_module_does_no_serialization():
    """The declared WS6 wire-boundary entry is retired: no to_camel_dict here."""
    import quodeq.services._projects_cache as mod

    assert "to_camel_dict" not in open(mod.__file__).read()


def test_route_serializes_entities_to_camel_case(tmp_path):
    """End-to-end: the /api/projects payload keeps its camelCase shape."""
    from flask import Flask

    from quodeq.api.routes_project_list import register_project_list_routes

    class _Provider:
        def list_projects(self, reports_dir, *, offset=0, limit=0):
            return {"projects": [_entry()]}

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["EVALUATIONS_DIR"] = str(tmp_path)
    register_project_list_routes(app, _Provider())

    body = app.test_client().get("/api/projects").get_json()

    assert body["projects"][0]["runsCount"] == 2
    assert body["projects"][0]["latestRunId"] == "r2"


def test_pending_summaries_keep_the_cache_cold(tmp_path):
    """While any entry is summary-pending the TTL must not stamp: the UI polls
    every few seconds for grades the warm-up engine is still computing."""
    pending = ProjectEntry(id="p1", name="proj", runs_count=2, latest_run_id="r2", summary_pending=True)
    with patch(
        "quodeq.services._projects_cache._fs_projects.build_project_list",
        return_value=[pending],
    ) as spy:
        cache = ProjectsCache()
        cache.list(str(tmp_path))
        cache.list(str(tmp_path))
    assert spy.call_count == 2, "pending entries must bypass the TTL window"


def test_settled_summaries_stamp_the_cache_again(tmp_path):
    done = ProjectEntry(id="p1", name="proj", runs_count=2, latest_run_id="r2", summary_pending=False)
    with patch(
        "quodeq.services._projects_cache._fs_projects.build_project_list",
        return_value=[done],
    ) as spy:
        cache = ProjectsCache()
        cache.list(str(tmp_path))
        cache.list(str(tmp_path))
    assert spy.call_count == 1


def test_summary_pending_serializes_camelcase():
    from quodeq.shared.serialization import to_camel_dict
    entry = ProjectEntry(id="p", name="p", summary_pending=True)
    assert to_camel_dict(entry)["summaryPending"] is True


def test_paginated_hydration_gets_the_index_auto_detected_parent():
    """Critical #1 regression (code review): _hydrate() must not silently
    return the raw, unenriched .parent that build_project_entries()/
    _build_project_entry() read straight off repository_info.json -- it
    must use the value build_project_index() already auto-detected.
    """
    index = [ProjectEntry(id="child", name="child", parent="parent")]
    raw_hydrated = [ProjectEntry(id="child", name="child", parent=None, runs_count=3)]
    with patch(
        "quodeq.services._projects_cache._fs_project_index.build_project_index",
        return_value=index,
    ), patch(
        "quodeq.services._projects_cache._fs_project_index.build_project_entries",
        return_value=raw_hydrated,
    ):
        out = ProjectsCache().list("/reports", offset=0, limit=10)

    entry = out["projects"][0]
    assert entry.parent == "parent"
    assert entry.runs_count == 3, "the rest of the hydrated entry must be untouched"


def test_hydrate_read_cannot_observe_a_concurrent_invalidate_mid_fill():
    """Critical #2 regression (code review): before the fix, the list
    comprehension that builds a paginated page read ``self._hydrated``
    *outside* ``_hydrate_lock`` -- a concurrent ``invalidate()`` (which took
    no lock at all) landing between "fill" and "read" could return a
    truncated or empty page with no error signal. Flask serves this app
    threaded by default, so this is a real, not theoretical, race.

    This pins down the fixed invariant: once a hydrate call has entered its
    critical section, ``invalidate()`` cannot interleave with it -- it can
    only run entirely before or entirely after. A pause is injected inside
    the (locked) build step and ``invalidate()`` is fired while that pause
    holds, from another thread; the page must still come back complete.
    """
    import threading

    index = [ProjectEntry(id=f"p{i}", name=f"p{i}") for i in range(3)]
    entered_build = threading.Event()
    release_build = threading.Event()

    def slow_build(_root, ids, **kwargs):
        entered_build.set()
        release_build.wait(timeout=2)
        return [ProjectEntry(id=i, name=i) for i in ids]

    with patch(
        "quodeq.services._projects_cache._fs_project_index.build_project_index",
        return_value=index,
    ), patch(
        "quodeq.services._projects_cache._fs_project_index.build_project_entries",
        side_effect=slow_build,
    ):
        cache = ProjectsCache()
        page: dict = {}

        def hit():
            page["result"] = cache.list("/reports", offset=0, limit=10)

        hydrate_thread = threading.Thread(target=hit)
        hydrate_thread.start()
        assert entered_build.wait(timeout=2), "build never started"

        invalidate_thread = threading.Thread(target=cache.invalidate)
        invalidate_thread.start()
        release_build.set()

        hydrate_thread.join(timeout=2)
        invalidate_thread.join(timeout=2)

    assert len(page["result"]["projects"]) == 3, (
        "a concurrent invalidate() must not truncate an in-flight page"
    )
