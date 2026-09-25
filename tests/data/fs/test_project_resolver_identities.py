"""The identities resolve_project_uuid records for parent, child and dot-child projects."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.project_resolver import ProjectIdentity, resolve_project_uuid

_REMOTE = "https://example.com/org/repo.git"


class _MemoryRepo:
    """A ProjectRepository kept in memory."""

    def __init__(self) -> None:
        self.index: dict[str, str] = {}

    def load_index(self, reports_dir: Path) -> dict[str, str]:
        return dict(self.index)

    def save_index(self, reports_dir: Path, index: dict[str, str]) -> None:
        self.index = dict(index)


def _info(reports: Path, project_uuid: str) -> dict:
    return json.loads((reports / project_uuid / "repository_info.json").read_text(encoding="utf-8"))


def _identity(repo: Path, scope_path: str | None = None) -> ProjectIdentity:
    return ProjectIdentity("proj", str(repo), "code", scope_path=scope_path, remote_url=_REMOTE)


def test_scoped_resolution_records_an_unscoped_parent_and_a_linked_child(tmp_path):
    reports, repo = tmp_path / "reports", tmp_path / "repo"
    repo.mkdir()
    store = _MemoryRepo()

    child_uuid = resolve_project_uuid(reports, _identity(repo, "src"), repository=store)

    child = _info(reports, child_uuid)
    parent = _info(reports, child["parent"])
    assert parent == {
        "uuid": child["parent"], "name": "proj", "discipline": "code", "location": "local",
        "path": str(repo.resolve()), "remote_url": _REMOTE,
    }
    assert child["name"] == "proj/src"
    assert child["scopePath"] == "src"
    assert child["remote_url"] == _REMOTE
    assert resolve_project_uuid(reports, _identity(repo, "src"), repository=store) == child_uuid


def test_unscoped_resolution_with_children_records_a_dot_child(tmp_path):
    reports, repo = tmp_path / "reports", tmp_path / "repo"
    repo.mkdir()
    store = _MemoryRepo()
    child_uuid = resolve_project_uuid(reports, _identity(repo, "src"), repository=store)
    parent_uuid = _info(reports, child_uuid)["parent"]

    dot_uuid = resolve_project_uuid(reports, _identity(repo), repository=store)

    dot = _info(reports, dot_uuid)
    assert dot["name"] == "proj/."
    assert dot["scopePath"] == "."
    assert dot["parent"] == parent_uuid
    assert dot["path"] == str(repo.resolve())
    assert resolve_project_uuid(reports, _identity(repo), repository=store) == dot_uuid
