"""Tests for fs_projects.py: get_project_info and the ProjectEntry origin_url / latest_done_run_id fields."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from quodeq.services.fs_projects import (
    build_project_list,
    get_project_info,
)


# ---------------------------------------------------------------------------
# get_project_info
# ---------------------------------------------------------------------------


class TestGetProjectInfo:
    def test_returns_info(self, tmp_path: Path):
        proj = tmp_path / "proj-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text(json.dumps({
            "name": "test",
            "discipline": "software",
            "location": "local",
            "path": str(tmp_path),
        }))
        result = get_project_info(
            str(tmp_path), "proj-uuid",
            list_dimensions=lambda **_kw: ["sec"],
            has_fingerprints=lambda *_a: False,
        )
        assert result is not None
        assert result["name"] == "test"
        assert result["discipline"] == "software"
        assert result["availableDimensions"] == ["sec"]
        assert result["hasFingerprints"] is False

    def test_returns_none_for_missing(self, tmp_path: Path):
        assert get_project_info(str(tmp_path), "nope") is None

    def test_returns_none_for_corrupt_json(self, tmp_path: Path):
        proj = tmp_path / "proj-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text("not json")
        assert get_project_info(str(tmp_path), "proj-uuid") is None

    def test_path_missing_detection(self, tmp_path: Path):
        proj = tmp_path / "proj-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text(json.dumps({
            "name": "test",
            "location": "online",
            "path": "/local/path",  # Not a URL
        }))
        with patch("quodeq.services.fs_projects.infer_discipline", return_value=None):
            result = get_project_info(
                str(tmp_path), "proj-uuid",
                list_dimensions=lambda **_kw: [],
                has_fingerprints=lambda *_a: False,
            )
        assert result is not None
        assert result["pathMissing"] is True

    def test_traversal_rejected(self, tmp_path: Path):
        result = get_project_info(str(tmp_path), "../escape")
        assert result is None


# ---------------------------------------------------------------------------
# ProjectEntry.origin_url
# ---------------------------------------------------------------------------


def test_project_entry_carries_origin_url(tmp_path):
    from quodeq.shared.serialization import to_camel_dict

    proj = tmp_path / "p1"
    run = proj / "run-1"
    run.mkdir(parents=True)
    (proj / "repository_info.json").write_text(
        json.dumps({"name": "p1", "originUrl": "https://github.com/example/p1.git"})
    )
    (run / "status.json").write_text(json.dumps({"schema_version": 2, "state": "done"}))

    entries = build_project_list(tmp_path)
    entry = next(e for e in entries if e.id == "p1")
    assert entry.origin_url == "https://github.com/example/p1.git"
    assert to_camel_dict(entry)["originUrl"] == "https://github.com/example/p1.git"


# ---------------------------------------------------------------------------
# ProjectEntry.latest_done_run_id
# ---------------------------------------------------------------------------


def _make_run(proj: Path, run_id: str, *, state: str | None) -> None:
    """Create a manifest-bearing run directory, optionally with a status.json state."""
    run = proj / run_id
    (run / "evidence").mkdir(parents=True)
    (run / "evidence" / "manifest.json").write_text("{}")
    if state is not None:
        (run / "status.json").write_text(json.dumps({"schema_version": 2, "state": state}))


def test_latest_done_run_id_is_newest_done_run_not_newest_run(tmp_path: Path):
    # Publish run A (done). Run B is newer but cancelled. latestRunId must
    # still reflect B (any status), but latestDoneRunId must fall back to A --
    # otherwise the shared-vs-local comparison could never converge once a
    # later run fails or is cancelled.
    proj = tmp_path / "p1"
    proj.mkdir()
    (proj / "repository_info.json").write_text(json.dumps({"name": "p1"}))
    _make_run(proj, "20260301", state="done")
    _make_run(proj, "20260302", state="cancelled")

    entries = build_project_list(tmp_path)
    entry = next(e for e in entries if e.id == "p1")
    assert entry.latest_run_id == "20260302"
    assert entry.latest_done_run_id == "20260301"


def test_latest_done_run_id_absent_when_no_done_runs(tmp_path: Path):
    from quodeq.shared.serialization import to_camel_dict

    proj = tmp_path / "p2"
    proj.mkdir()
    (proj / "repository_info.json").write_text(json.dumps({"name": "p2"}))
    _make_run(proj, "20260301", state="cancelled")

    entries = build_project_list(tmp_path)
    entry = next(e for e in entries if e.id == "p2")
    assert entry.latest_run_id == "20260301"
    assert entry.latest_done_run_id is None
    assert "latestDoneRunId" not in to_camel_dict(entry)
