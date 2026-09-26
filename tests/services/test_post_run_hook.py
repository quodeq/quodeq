"""PostRunHook.__call__: a cleanup_clone failure must not block project_events.

Its call was previously unguarded, so a cleanup failure skipped
project_events (the State Store projection) two lines below entirely. The
fix guards cleanup_clone with `except OSError` (matching the filesystem
errors remove_clone_dir/get_clones_dir can raise) and project_events with
`except (sqlite3.Error, OSError, ValueError)` (matching Projector's sqlite
and JSON/file failures). Anything outside those tuples is a programming
error and propagates so JobManager sees it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quodeq.services._post_run_hook import PostRunHook


class _Job:
    def __init__(self, project: str, run_id: str) -> None:
        self.output_project = project
        self.output_run_id = run_id


class TestCleanupCloneFailSoft:
    def test_cleanup_clone_failure_does_not_block_project_events(self, tmp_path: Path, monkeypatch):
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(
            hook, "cleanup_clone", MagicMock(side_effect=OSError("clone dir busy")),
        )
        events_called = []
        monkeypatch.setattr(
            hook, "project_events",
            lambda job, reports: events_called.append((job, reports)),
        )
        job = _Job("proj-uuid", "run-1")

        hook("job-1", job)  # must not raise

        assert events_called == [(job, tmp_path)]

    def test_cleanup_clone_failure_is_logged_with_job_id(self, tmp_path: Path, monkeypatch, caplog):
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(
            hook, "cleanup_clone", MagicMock(side_effect=OSError("clone dir busy")),
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
            lambda job, reports: events_called.append((job, reports)),
        )
        job = _Job("proj-uuid", "run-1")

        hook("job-1", job)

        assert cleanup_calls == [("proj-uuid", tmp_path)]
        assert events_called == [(job, tmp_path)]

    def test_cleanup_clone_unnamed_exception_propagates(self, tmp_path: Path, monkeypatch):
        """A RuntimeError from cleanup_clone is outside the (OSError,) tuple: it is a
        programming error, not the best-effort filesystem cleanup the catch guards."""
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(
            hook, "cleanup_clone", MagicMock(side_effect=RuntimeError("bug")),
        )
        job = _Job("proj-uuid", "run-1")

        with pytest.raises(RuntimeError, match="bug"):
            hook("job-1", job)


class TestProjectEventsFailSoft:
    @pytest.mark.parametrize("exc", [sqlite3.Error("db locked"), OSError("no space"), ValueError("bad json")])
    def test_project_events_named_failure_is_logged_not_raised(self, tmp_path: Path, monkeypatch, caplog, exc):
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(hook, "cleanup_clone", lambda *a, **kw: None)
        monkeypatch.setattr(
            hook, "project_events", MagicMock(side_effect=exc),
        )
        job = _Job("proj-uuid", "run-1")

        with caplog.at_level("WARNING", logger="quodeq.services._post_run_hook"):
            hook("job-1", job)  # must not raise

        assert any("job-1" in r.message for r in caplog.records)

    def test_project_events_unnamed_exception_propagates(self, tmp_path: Path, monkeypatch):
        """A RuntimeError from project_events is outside the (sqlite3.Error, OSError,
        ValueError) tuple and must propagate rather than hide a real bug behind a
        silent State Store gap."""
        hook = PostRunHook(reports_root=tmp_path)
        monkeypatch.setattr(hook, "cleanup_clone", lambda *a, **kw: None)
        monkeypatch.setattr(
            hook, "project_events", MagicMock(side_effect=RuntimeError("bug")),
        )
        job = _Job("proj-uuid", "run-1")

        with pytest.raises(RuntimeError, match="bug"):
            hook("job-1", job)
