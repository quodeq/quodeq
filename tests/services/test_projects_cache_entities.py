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
        def list_projects(self, reports_dir):
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
