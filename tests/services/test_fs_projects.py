"""Tests for fs_projects.py — project listing (find_children, parent/child sets, build_project_list, index)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from quodeq.services._fs_project_index import build_project_index
from quodeq.services.fs_projects import (
    _build_parent_child_sets,
    build_project_list,
)
from quodeq.services.wiring import find_children


# ---------------------------------------------------------------------------
# find_children
# ---------------------------------------------------------------------------


class TestFindChildren:
    def test_finds_children(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        child = tmp_path / "child-uuid"
        child.mkdir()
        (child / "repository_info.json").write_text(json.dumps({"parent": "parent-uuid"}))
        # Unrelated project
        other = tmp_path / "other-uuid"
        other.mkdir()
        (other / "repository_info.json").write_text(json.dumps({"parent": "someone-else"}))

        result = find_children(tmp_path, "parent-uuid")
        assert result == ["child-uuid"]

    def test_no_children(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        assert find_children(tmp_path, "parent-uuid") == []

    def test_skips_corrupt_json(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        child = tmp_path / "child-uuid"
        child.mkdir()
        (child / "repository_info.json").write_text("not json")
        assert find_children(tmp_path, "parent-uuid") == []

    def test_skips_missing_info(self, tmp_path: Path):
        parent = tmp_path / "parent-uuid"
        parent.mkdir()
        child = tmp_path / "child-uuid"
        child.mkdir()
        # No repository_info.json
        assert find_children(tmp_path, "parent-uuid") == []


# ---------------------------------------------------------------------------
# _build_parent_child_sets
# ---------------------------------------------------------------------------


class TestBuildParentChildSets:
    def test_identifies_parents_and_children(self, tmp_path: Path):
        (tmp_path / "child1").mkdir()
        (tmp_path / "child1" / "repository_info.json").write_text(
            json.dumps({"parent": "parent-uuid"})
        )
        (tmp_path / "standalone").mkdir()
        (tmp_path / "standalone" / "repository_info.json").write_text(
            json.dumps({"name": "standalone"})
        )
        parents, subs, info_by_name = _build_parent_child_sets(tmp_path, ["child1", "standalone"])
        assert parents == {"parent-uuid"}
        assert subs == {"child1"}
        assert "child1" in info_by_name
        assert "standalone" in info_by_name
        assert info_by_name["child1"]["parent"] == "parent-uuid"

    def test_empty_dirs(self, tmp_path: Path):
        parents, subs, info_by_name = _build_parent_child_sets(tmp_path, [])
        assert parents == set()
        assert subs == set()
        assert info_by_name == {}

    def test_corrupt_json_skipped(self, tmp_path: Path):
        (tmp_path / "bad").mkdir()
        (tmp_path / "bad" / "repository_info.json").write_text("{{{")
        parents, subs, info_by_name = _build_parent_child_sets(tmp_path, ["bad"])
        assert parents == set()
        assert subs == set()
        assert "bad" not in info_by_name


# ---------------------------------------------------------------------------
# build_project_list
# ---------------------------------------------------------------------------


class TestBuildProjectList:
    def test_includes_registered_project_with_no_runs(self, tmp_path: Path):
        # A project registered by the onboarding wizard (POST /api/projects)
        # has repository_info.json but no runs yet — it must still appear in
        # the projects list so the UI can show its empty state immediately.
        proj = tmp_path / "fresh-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text(json.dumps({
            "name": "fresh",
            "path": str(tmp_path),
            "location": "local",
            "onboardingCompletedAt": None,
        }))
        entries = build_project_list(tmp_path)
        entry = next((e for e in entries if e.id == "fresh-uuid"), None)
        assert entry is not None
        assert entry.runs_count == 0
        assert entry.latest_run_id is None
        assert entry.onboarding_completed_at is None

    def test_excludes_dir_without_repo_info_or_runs(self, tmp_path: Path):
        (tmp_path / "junk-dir").mkdir()
        assert build_project_list(tmp_path) == []

    def test_reads_repository_info_once_per_directory(self, tmp_path: Path):
        # Regression test: ensure build_project_list() reads repository_info.json
        # at most once per directory, not multiple times (deduplication).
        proj1 = tmp_path / "proj1-uuid"
        proj1.mkdir()
        (proj1 / "repository_info.json").write_text(json.dumps({
            "name": "proj1",
            "path": str(tmp_path),
            "location": "local",
        }))
        proj2 = tmp_path / "proj2-uuid"
        proj2.mkdir()
        (proj2 / "repository_info.json").write_text(json.dumps({
            "name": "proj2",
            "path": str(tmp_path),
            "location": "local",
            "parent": "parent-uuid",
        }))

        call_count: dict[str, int] = {}

        with patch("quodeq.services.fs_projects.read_repository_info") as mock_read:
            with patch("quodeq.services.fs_project_helpers.read_repository_info") as mock_read_helpers:
                def side_effect(path):
                    dir_name = path.name
                    call_count[dir_name] = call_count.get(dir_name, 0) + 1
                    if path.is_dir() and (path / "repository_info.json").exists():
                        return json.loads((path / "repository_info.json").read_text())
                    return None

                mock_read.side_effect = side_effect
                mock_read_helpers.side_effect = side_effect
                build_project_list(tmp_path)

        # Each directory should be read at most once
        assert call_count.get("proj1-uuid", 0) <= 1, f"proj1-uuid read {call_count.get('proj1-uuid', 0)} times"
        assert call_count.get("proj2-uuid", 0) <= 1, f"proj2-uuid read {call_count.get('proj2-uuid', 0)} times"


# ---------------------------------------------------------------------------
# _build_one fail-soft (one bad project dir must not fail the
# whole listing)
# ---------------------------------------------------------------------------


class TestBuildProjectListFailSoft:
    def test_one_bad_project_dir_is_skipped_not_fatal(self, tmp_path: Path, caplog):
        """A project whose entry build raises is logged and skipped; every
        other project still comes back -- mirrors score_run.py's
        _score_one_dimension fail-soft handling."""
        good = tmp_path / "good-uuid"
        good.mkdir()
        (good / "repository_info.json").write_text(json.dumps({
            "name": "good", "path": str(tmp_path), "location": "local",
        }))
        bad = tmp_path / "bad-uuid"
        bad.mkdir()
        (bad / "repository_info.json").write_text(json.dumps({
            "name": "bad", "path": str(tmp_path), "location": "local",
        }))

        import quodeq.services.fs_projects as mod
        real_build = mod._build_project_entry

        def side_effect(reports_root, entry_name, runs, options, **kwargs):
            if entry_name == "bad-uuid":
                raise OSError("simulated disk error reading bad-uuid")
            return real_build(reports_root, entry_name, runs, options, **kwargs)

        with patch("quodeq.services.fs_projects._build_project_entry", side_effect=side_effect):
            with caplog.at_level("WARNING", logger="quodeq.services.fs_projects"):
                entries = build_project_list(tmp_path)

        ids = {e.id for e in entries}
        assert ids == {"good-uuid"}
        assert any("bad-uuid" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# build_project_index
# ---------------------------------------------------------------------------


class TestBuildProjectIndex:
    def test_reads_repository_info_once_per_directory(self, tmp_path: Path, monkeypatch):
        # The parent/child pass already parses every record; the entry pass
        # must reuse it instead of re-reading the same file.
        for name, extra in (("proj1-uuid", {}), ("proj2-uuid", {"parent": "parent-uuid"})):
            proj = tmp_path / name
            proj.mkdir()
            (proj / "repository_info.json").write_text(json.dumps({
                "name": name, "path": str(tmp_path), "location": "local", **extra,
            }))

        reads: dict[str, int] = {}
        real_read_text = Path.read_text

        def counting_read_text(self, *args, **kwargs):
            if self.name == "repository_info.json":
                reads[self.parent.name] = reads.get(self.parent.name, 0) + 1
            return real_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", counting_read_text)
        entries = build_project_index(tmp_path)

        assert {e.id for e in entries} == {"proj1-uuid", "proj2-uuid"}
        assert reads == {"proj1-uuid": 1, "proj2-uuid": 1}

    def test_registered_dir_with_corrupt_record_is_still_listed(self, tmp_path: Path):
        # A corrupt repository_info.json still marks a registered project;
        # the index lists it with fallback metadata rather than dropping it.
        proj = tmp_path / "bad-uuid"
        proj.mkdir()
        (proj / "repository_info.json").write_text("{not json")
        entries = build_project_index(tmp_path)
        assert [e.id for e in entries] == ["bad-uuid"]
