"""Tests for quodeq.services._registration_scan.

``_scan_parent_project`` reads a project's ``repository_info.json`` to find
its parent UUID and, if the parent lacks a scan.json, scans it. That read
is genuinely best-effort (a missing/corrupt sidecar just means "no parent
scan to trigger"), but the failure must still be observable, not silently
dropped -- via an injected ``log: LogSink`` (SEP-06 inner-layer discipline;
``services/`` doesn't import a logging framework directly), not ``caplog``.
See ``tests.conftest.RecordingLog`` / the ``recording_log`` fixture.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.services._registration_scan import _scan_parent_project


def test_scan_parent_project_logs_on_corrupt_repository_info(tmp_path, recording_log):
    """A malformed repository_info.json must be logged, not swallowed silently."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    info_path = project_dir / "repository_info.json"
    info_path.write_text("{not valid json", encoding="utf-8")

    reports_path = tmp_path / "reports"
    repo_path = tmp_path / "repo"

    _scan_parent_project(project_dir, reports_path, repo_path, log=recording_log)

    assert any(
        "parent project" in m.lower() and str(info_path) in m
        for m in recording_log.warning_messages
    ), f"expected a warning naming {info_path}, got: {recording_log.warning_messages}"


def test_scan_parent_project_logs_on_missing_repository_info(tmp_path, recording_log):
    """A missing repository_info.json raises OSError (FileNotFoundError) and must log too."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()  # no repository_info.json written

    reports_path = tmp_path / "reports"
    repo_path = tmp_path / "repo"

    _scan_parent_project(project_dir, reports_path, repo_path, log=recording_log)

    assert any("parent project" in m.lower() for m in recording_log.warning_messages)


def test_scan_parent_project_no_op_when_no_parent(tmp_path, recording_log):
    """Sanity check: a well-formed sidecar with no parent is silent (no log, no scan)."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "repository_info.json").write_text("{}", encoding="utf-8")

    reports_path = tmp_path / "reports"
    repo_path = tmp_path / "repo"

    _scan_parent_project(project_dir, reports_path, repo_path, log=recording_log)

    assert recording_log.warning_messages == []


def test_scan_parent_project_defaults_to_null_log(tmp_path):
    """No log passed -> NULL_LOG default, so a corrupt sidecar must not raise."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "repository_info.json").write_text("{not valid json", encoding="utf-8")

    reports_path = tmp_path / "reports"
    repo_path = tmp_path / "repo"

    _scan_parent_project(project_dir, reports_path, repo_path)  # must not raise
