"""POST /api/evaluations names WHICH repository problem it hit.

The service raises FileNotFoundError for a path that is missing or is a
file, and ValueError for a git url (an evaluation needs the registered
local copy). The route used to fold all of them into one "Invalid
repository" sentence under INVALID_INPUT, which hid the fix from the user.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.services.base import ActionProvider
from quodeq.shared.utils import is_repo_url

_ORIGIN = {"Origin": "http://localhost"}


class _MirrorProvider(ActionProvider):
    """Raises exactly what services.evaluation_mixin raises for a bad target."""

    def list_projects(self, reports_dir):
        return {"projects": []}

    def get_project_info(self, reports_dir, project):
        return {}

    def start_evaluation(self, repo, reports_dir, options):
        if is_repo_url(repo):
            raise ValueError("URL repos are not supported here.")
        if not Path(repo).resolve().exists():
            raise FileNotFoundError(f"Repository not found: {repo}")
        if not Path(repo).is_dir():
            raise FileNotFoundError(f"Repo path points at a file, not a directory: {repo}")
        return {"jobId": "test-job", "status": "running", "logs": []}

    def get_evaluation_status(self, job_id, reports_dir=None):
        return None

    def cancel_evaluation(self, job_id, reports_dir=None, discard_partial=False, wait_for_exit=False):
        return False

    def list_evaluations(self, *, limit=0, reports_dir=None, states=None):
        return []

    def delete_project(self, reports_dir, project):
        return False


@pytest.fixture()
def client(monkeypatch, tmp_path):
    # The route's scan allowlist accepts paths under the home folder; point
    # it at tmp_path so the tests never touch the real home.
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("QUODEQ_API_KEY", raising=False)
    return create_app(_MirrorProvider()).test_client()


def _start(client, repo: str):
    return client.post("/api/evaluations", json={"repo": repo, "dimensions": ["security"]}, headers=_ORIGIN)


def test_a_missing_folder_answers_path_missing(client):
    r = _start(client, str(Path.home() / "no-such-folder"))
    assert r.status_code == 400
    body = r.get_json()
    assert body["code"] == "PATH_MISSING"
    assert "no-such-folder" not in body["error"]


def test_a_file_answers_not_a_directory(client):
    target = Path.home() / "notes.txt"
    target.write_text("hello")
    r = _start(client, str(target))
    assert r.status_code == 400
    assert r.get_json()["code"] == "NOT_DIR"


def test_a_git_url_answers_url_not_evaluable(client):
    r = _start(client, "https://github.com/octocat/Hello-World.git")
    assert r.status_code == 400
    body = r.get_json()
    assert body["code"] == "URL_NOT_EVALUABLE"
    assert "project" in body["error"].lower()


def test_a_folder_that_exists_starts(client):
    folder = Path.home() / "repo"
    folder.mkdir()
    r = _start(client, str(folder))
    assert r.status_code == 202
