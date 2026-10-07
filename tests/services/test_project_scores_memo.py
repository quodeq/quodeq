"""get_project_scores memoizes the full payload on a stamp of its inputs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.services.dismissed import dismiss_finding
from quodeq.services.scoring import get_project_scores, get_project_scores_stamped
from quodeq.services.scoring_deps import ScoringDeps
from quodeq.shared.stamp_memo import StampCache

RUN = "20260101T000000"
_MODULE = "quodeq.services.scoring._project_scores"


def _write_run(reports: Path, project: str = "proj", run_id: str = RUN, state: str = "done") -> Path:
    run_dir = reports / project / run_id
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    violations = [
        {"principle": "N/A", "req": "N/A", "file": "src/a.py", "line": 73, "title": "Arbitrary file read", "severity": "critical"},
        {"principle": "Modularity", "req": "M-MOD-1", "file": "src/b.py", "line": 5, "title": "Oversized function", "severity": "major"},
    ]
    (eval_dir / "maintainability.json").write_text(json.dumps({
        "dimension": "maintainability", "overallScore": "6.0/10", "overallGrade": "Fair",
        "principles": [], "violations": violations, "compliance": [],
        "totals": {"violationCount": 2, "complianceCount": 0, "severity": {"critical": 1, "major": 1, "minor": 0}},
    }), encoding="utf-8")
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text('{"language_stats": {}}', encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps({"state": state, "dateISO": "2026-01-01T00:00:00Z"}))
    return run_dir


@pytest.fixture(autouse=True)
def _fresh_memo():
    with patch(f"{_MODULE}._PAYLOADS", StampCache()):
        yield


# A memo hit hands back the very same payload object; a rebuild is a new one.
def test_second_request_reuses_the_payload(tmp_path: Path) -> None:
    _write_run(tmp_path)
    first, stamp1 = get_project_scores_stamped(tmp_path, "proj")
    second, stamp2 = get_project_scores_stamped(tmp_path, "proj")
    assert first is second and stamp1 == stamp2


def test_dismissal_changes_the_stamp_and_recomputes(tmp_path: Path) -> None:
    _write_run(tmp_path)
    first, stamp1 = get_project_scores_stamped(tmp_path, "proj")
    dismiss_finding(tmp_path / "proj", {"req": "N/A", "file": "src/a.py", "line": 73})
    payload, stamp2 = get_project_scores_stamped(tmp_path, "proj")
    assert stamp2 != stamp1 and payload is not first
    assert payload["accumulated"]["dimensions"][0]["totals"]["violationCount"] == 1


def test_run_status_change_alone_changes_the_stamp(tmp_path: Path) -> None:
    # A run is RUNNING while a live process holds its pid (status.json only
    # settles terminal states), so the pid resolver is what flips here.
    _write_run(tmp_path, state="running")
    with patch("quodeq.data.fs.report_parser.runs.resolve_external_pid", return_value=os.getpid()):
        first, stamp1 = get_project_scores_stamped(tmp_path, "proj")
    assert str(first["availableRuns"][0]["status"]) == "running"
    with patch("quodeq.data.fs.report_parser.runs.resolve_external_pid", return_value=None):
        second, stamp2 = get_project_scores_stamped(tmp_path, "proj")
    assert stamp2 != stamp1
    assert str(second["availableRuns"][0]["status"]) == "done"


def test_incomplete_rescore_is_not_memoized(tmp_path: Path) -> None:
    """A winning run whose full read lacks a graded dimension is served, not memoized."""
    _write_run(tmp_path)
    deps = ScoringDeps(base_fetcher_factory=lambda _rr, _p: (lambda _run_id: []))
    first, _ = get_project_scores_stamped(tmp_path, "proj", None, deps)
    second, _ = get_project_scores_stamped(tmp_path, "proj", None, deps)
    assert first is not None and first is not second


def test_missing_and_empty_projects_have_no_stamp(tmp_path: Path) -> None:
    assert get_project_scores_stamped(tmp_path, "nope") == (None, None)
    (tmp_path / "empty").mkdir()
    payload, stamp = get_project_scores_stamped(tmp_path, "empty")
    assert stamp is None and payload["availableRuns"] == []


def test_get_project_scores_still_returns_the_payload(tmp_path: Path) -> None:
    _write_run(tmp_path)
    assert get_project_scores(tmp_path, "proj")["availableRuns"][0]["runId"] == RUN


def test_a_running_run_writing_files_changes_the_stamp(tmp_path: Path) -> None:
    # A run in flight has no version of its own in the accumulated cache key
    # (only touching suppressions count), so its files are stamped directly:
    # the trend point for that run must follow what it has scored so far.
    run_dir = _write_run(tmp_path, state="running")
    with patch("quodeq.data.fs.report_parser.runs.resolve_external_pid", return_value=os.getpid()):
        first, stamp1 = get_project_scores_stamped(tmp_path, "proj")
        (run_dir / "evaluation" / "security.json").write_text(json.dumps({
            "dimension": "security", "overallScore": "8.0/10", "overallGrade": "Good",
            "principles": [], "violations": [], "compliance": [],
        }), encoding="utf-8")
        second, stamp2 = get_project_scores_stamped(tmp_path, "proj")
    assert stamp2 != stamp1 and second is not first


def test_as_of_requests_are_not_memoized(tmp_path: Path) -> None:
    # One entry per project keeps the memo small; as-of payloads are frozen
    # client-side already.
    _write_run(tmp_path)
    payload, stamp = get_project_scores_stamped(tmp_path, "proj", RUN)
    assert stamp is None and payload["availableRuns"][0]["runId"] == RUN
    again, _ = get_project_scores_stamped(tmp_path, "proj", RUN)
    assert again is not payload


def test_parent_projects_are_not_memoized(tmp_path: Path) -> None:
    _write_run(tmp_path)
    with patch(f"{_MODULE}.find_children", return_value=["child"]), \
         patch(f"{_MODULE}.per_run_versions") as versions:
        payload, stamp = get_project_scores_stamped(tmp_path, "proj")
    assert stamp is None and payload is not None
    versions.assert_not_called()


# A detail page asks /compliance-detail once per dimension and kind, all at
# once. On a memo miss every request used to build the whole payload for
# itself, beside the others; the first now builds and the rest wait and read.
def test_concurrent_misses_build_the_payload_once(tmp_path: Path) -> None:
    import threading
    import time

    from quodeq.services.dashboard import make_run_dimension_fetcher

    _write_run(tmp_path)
    factory_calls: list[float] = []
    guard = threading.Lock()

    def counting_factory(reports_root: Path, project: str):
        with guard:
            factory_calls.append(time.monotonic())
        time.sleep(0.05)
        return make_run_dimension_fetcher(reports_root, project)

    deps = ScoringDeps(base_fetcher_factory=counting_factory)
    # One build asks the factory for the trend's reader and the accumulated
    # block's; a single sequential read says how many times that is.
    get_project_scores(tmp_path, "proj", None, deps)
    per_build = len(factory_calls)
    assert per_build >= 1
    factory_calls.clear()

    results: list[dict] = []

    def read() -> None:
        results.append(get_project_scores(tmp_path, "proj", None, deps))

    with patch(f"{_MODULE}._PAYLOADS", StampCache()):
        threads = [threading.Thread(target=read) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(factory_calls) == per_build
    assert len(results) == 6
    assert all(r is results[0] for r in results)
