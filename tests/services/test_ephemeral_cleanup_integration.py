"""Integration tests for ``maybe_cleanup_after_job``.

These verify the post-evaluation cleanup helper that the JobManager
on-complete callback delegates to: ephemeral clones are removed,
non-ephemeral checkouts are left alone, and missing/corrupt info
files are tolerated as no-ops.
"""

from __future__ import annotations

import json
from pathlib import Path

from quodeq.services._ephemeral_cleanup import maybe_cleanup_after_job


def _write_info(reports_root: Path, uuid: str, *, ephemeral: bool, path: str) -> None:
    d = reports_root / uuid
    d.mkdir(parents=True, exist_ok=True)
    (d / "repository_info.json").write_text(
        json.dumps({"location": "local", "ephemeral": ephemeral, "path": path})
    )


def test_cleanup_deletes_ephemeral_clone_after_job(tmp_path):
    reports = tmp_path / "reports"
    clone = tmp_path / "home" / ".quodeq" / "clones" / "uuid-1"
    clone.mkdir(parents=True)
    (clone / "file.py").write_text("x")
    _write_info(reports, "uuid-1", ephemeral=True, path=str(clone))

    maybe_cleanup_after_job(
        reports_root=reports, project_uuid="uuid-1", clones_root=clone.parent
    )

    assert not clone.exists()


def test_cleanup_skips_non_ephemeral_project(tmp_path):
    reports = tmp_path / "reports"
    repo = tmp_path / "code" / "myrepo"
    repo.mkdir(parents=True)
    (repo / "file.py").write_text("x")
    _write_info(reports, "uuid-2", ephemeral=False, path=str(repo))

    maybe_cleanup_after_job(
        reports_root=reports, project_uuid="uuid-2", clones_root=tmp_path / "clones"
    )

    assert repo.exists()  # untouched


def test_cleanup_handles_missing_info_file(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    # no project dir, no info file
    maybe_cleanup_after_job(
        reports_root=reports,
        project_uuid="missing",
        clones_root=tmp_path / "clones",
    )  # must not raise


def test_cleanup_handles_corrupt_info_json(tmp_path):
    reports = tmp_path / "reports"
    (reports / "uuid-3").mkdir(parents=True)
    (reports / "uuid-3" / "repository_info.json").write_text("not valid json {{{")
    maybe_cleanup_after_job(
        reports_root=reports,
        project_uuid="uuid-3",
        clones_root=tmp_path / "clones",
    )  # must not raise
