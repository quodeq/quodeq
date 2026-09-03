"""Tests for the onboardingCompletedAt heal in _build_project_entry.

A wizard-created project gets ``onboardingCompletedAt: null`` at registration
time. Setup completion is stamped when an evaluation starts (see
evaluation_mixin), but records created before that stamp existed are stuck at
null forever despite having runs. The list read heals those: null + runs =>
timestamp. Run-less records stay null (they are genuinely mid-setup), and the
shared-repo route (backfill=False) never writes.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

from quodeq.services._fs_project_helpers import _build_project_entry, find_existing_project
from quodeq.data.fs.report_parser.runs import RunInfo


def _make_project(tmp_path: Path, name: str = "proj-1", *, onboarding=None) -> Path:
    project_dir = tmp_path / name
    project_dir.mkdir()
    (project_dir / "repository_info.json").write_text(json.dumps({
        "name": name,
        "location": "local",
        "path": str(tmp_path / "src" / name),
        "onboardingCompletedAt": onboarding,
    }))
    return project_dir


def _run(run_id: str, date_iso: str | None) -> RunInfo:
    return RunInfo(run_id=run_id, date_iso=date_iso, date_label=run_id)


def _read_field(project_dir: Path):
    return json.loads((project_dir / "repository_info.json").read_text())["onboardingCompletedAt"]


def test_entry_heals_null_onboarding_to_first_run_date(tmp_path):
    project_dir = _make_project(tmp_path, onboarding=None)
    # list_runs order: newest first, so the last element is the first run.
    runs = [
        _run("2026-01-05_00-00-00", "2026-01-05T00:00:00"),
        _run("2025-12-02_00-00-00", "2025-12-02T00:00:00"),
    ]

    entry = _build_project_entry(tmp_path, "proj-1", runs)

    assert entry.onboarding_completed_at == "2025-12-02T00:00:00"
    assert _read_field(project_dir) == "2025-12-02T00:00:00"


def test_entry_heals_null_onboarding_without_run_date(tmp_path):
    """A run with no parseable date still proves an evaluation happened."""
    project_dir = _make_project(tmp_path, onboarding=None)

    entry = _build_project_entry(tmp_path, "proj-1", [_run("some-run", None)])

    assert isinstance(entry.onboarding_completed_at, str) and entry.onboarding_completed_at
    assert _read_field(project_dir) == entry.onboarding_completed_at


def test_entry_keeps_null_onboarding_without_runs(tmp_path):
    project_dir = _make_project(tmp_path, onboarding=None)

    entry = _build_project_entry(tmp_path, "proj-1", [])

    assert entry.onboarding_completed_at is None
    assert _read_field(project_dir) is None


def test_entry_preserves_existing_onboarding_stamp(tmp_path):
    project_dir = _make_project(tmp_path, onboarding="2025-11-01T00:00:00Z")

    entry = _build_project_entry(
        tmp_path, "proj-1", [_run("2025-12-02_00-00-00", "2025-12-02T00:00:00")],
    )

    assert entry.onboarding_completed_at == "2025-11-01T00:00:00Z"
    assert _read_field(project_dir) == "2025-11-01T00:00:00Z"


def test_entry_backfill_false_never_writes(tmp_path):
    """The shared-repo route lists clones read-only: no heal, no dirty worktree."""
    project_dir = _make_project(tmp_path, onboarding=None)
    info_path = project_dir / "repository_info.json"
    before = info_path.read_text()

    entry = _build_project_entry(
        tmp_path, "proj-1",
        [_run("2025-12-02_00-00-00", "2025-12-02T00:00:00")],
        backfill=False,
    )

    assert entry.onboarding_completed_at is None
    assert info_path.read_text() == before


def test_find_existing_project_logs_malformed_repo_identifier(caplog, tmp_path):
    """A repo identifier is_repo_url can't classify must not fail silently:
    the duplicate check falls back to 'no match', but an operator needs a
    trace to see which malformed identifier was rejected."""
    with patch(
        "quodeq.shared.utils.is_repo_url",
        side_effect=ValueError("cannot classify repo identifier"),
    ), caplog.at_level(logging.WARNING):
        result = find_existing_project(str(tmp_path), "not a valid repo!!", None)
    assert result is None
    assert any("not a valid repo!!" in r.message for r in caplog.records)
