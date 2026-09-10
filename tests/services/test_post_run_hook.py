"""PostRunHook.__call__: a cleanup_clone failure must not block project_events.

Cluster 10 (fault-tolerance cycle 1): cleanup_clone's call was previously
unguarded, so a cleanup failure skipped project_events (the State Store
projection) two lines below entirely. The fix mirrors the existing
`except Exception: _logger.warning(..., exc_info=True)` guard already in
place around project_events.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from quodeq.services._post_run_hook import PostRunHook


class _Job:
    def __init__(self, project: str, run_id: str) -> None:
        self.output_project = project
        self.output_run_id = run_id


class TestCleanupCloneFailSoft:
    def test_cleanup_clone_failure_does_not_block_project_events(self, tmp_path: Path, monkeypatch):
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(
            hook, "cleanup_clone", MagicMock(side_effect=RuntimeError("clone dir busy")),
        )
        events_called = []
        monkeypatch.setattr(
            hook, "project_events",
            lambda job_id, job, reports: events_called.append((job_id, job, reports)),
        )
        job = _Job("proj-uuid", "run-1")

        hook("job-1", job)  # must not raise

        assert events_called == [("job-1", job, tmp_path)]

    def test_cleanup_clone_failure_is_logged_with_job_id(self, tmp_path: Path, monkeypatch, caplog):
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(
            hook, "cleanup_clone", MagicMock(side_effect=RuntimeError("clone dir busy")),
        )
        monkeypatch.setattr(hook, "project_events", lambda *a, **kw: None)
        job = _Job("proj-uuid", "run-1")

        with caplog.at_level("WARNING", logger="quodeq.services._post_run_hook"):
            hook("job-1", job)

        assert any("job-1" in r.message for r in caplog.records)

    def test_cleanup_clone_success_still_runs_project_events(self, tmp_path: Path, monkeypatch):
        hook = PostRunHook(reports_root=tmp_path)
        cleanup_calls = []
        monkeypatch.setattr(
            hook, "cleanup_clone",
            lambda project_uuid, reports: cleanup_calls.append((project_uuid, reports)),
        )
        events_called = []
        monkeypatch.setattr(
            hook, "project_events",
            lambda job_id, job, reports: events_called.append((job_id, job, reports)),
        )
        job = _Job("proj-uuid", "run-1")

        hook("job-1", job)

        assert cleanup_calls == [("proj-uuid", tmp_path)]
        assert events_called == [("job-1", job, tmp_path)]
