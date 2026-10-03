"""``find_existing_project``'s directory-walk fallback must tolerate a
malformed ``repository_info.json`` in one legacy project directory without
crashing the scan for the rest (REL-cycle-2 PR 4)."""
from __future__ import annotations

from pathlib import Path

from quodeq.data.fs.project_index import ProjectIdentity
from quodeq.data.fs.project_resolver import find_existing_project

_REPO_INFO_FILENAME = "repository_info.json"


class _Repo:
    """A ProjectRepository over two plain functions."""

    def __init__(self, load_fn, save_fn) -> None:
        self.load_index = load_fn
        self.save_index = save_fn


def _no_index_repo() -> _Repo:
    return _Repo(lambda reports_dir: {}, lambda reports_dir, index: None)


def test_scan_skips_a_non_object_repository_info_and_still_finds_the_match(tmp_path: Path):
    reports = tmp_path
    # A legacy project dir whose repository_info.json is syntactically valid
    # JSON but not an object -- `.get("name")` on it must not raise.
    broken = reports / "broken-uuid"
    broken.mkdir()
    (broken / _REPO_INFO_FILENAME).write_text("[1, 2, 3]", encoding="utf-8")

    # The real match, scanned after the broken entry.
    good = reports / "zzz-good-uuid"
    good.mkdir()
    (good / _REPO_INFO_FILENAME).write_text(
        '{"name": "proj", "path": "/repos/proj"}', encoding="utf-8",
    )

    identity = ProjectIdentity(project_name="proj", repo_path="/repos/proj")
    result = find_existing_project(reports, identity, _no_index_repo())
    assert result == "zzz-good-uuid"


def test_scan_skips_a_corrupt_repository_info_file(tmp_path: Path):
    reports = tmp_path
    broken = reports / "broken-uuid"
    broken.mkdir()
    (broken / _REPO_INFO_FILENAME).write_text("{ not json", encoding="utf-8")

    good = reports / "good-uuid"
    good.mkdir()
    (good / _REPO_INFO_FILENAME).write_text(
        '{"name": "proj", "path": "/repos/proj"}', encoding="utf-8",
    )

    identity = ProjectIdentity(project_name="proj", repo_path="/repos/proj")
    result = find_existing_project(reports, identity, _no_index_repo())
    assert result == "good-uuid"
