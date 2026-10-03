"""POST /api/projects with a file:// repository URL."""
from __future__ import annotations

import subprocess
from http import HTTPStatus

from tests.api.test_routes_project_clone import _ORIGIN, client, created  # noqa: F401 -- pytest fixtures

_MESSAGE = "That folder is not a git repository. Run git init there first, or point at a bare repository."


def _bare(tmp_path):
    origin = tmp_path.resolve() / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True, timeout=30)
    return origin


def test_a_local_bare_repo_starts_a_clone_job(client, created, tmp_path):
    r = client.post("/api/projects", json={"repo": f"file://{_bare(tmp_path)}"}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.ACCEPTED


def test_a_plain_folder_answers_not_a_git_repo(client, created, tmp_path):
    (tmp_path / "plain").mkdir()
    r = client.post("/api/projects", json={"repo": f"file://{tmp_path.resolve() / 'plain'}"}, headers=_ORIGIN)
    assert r.status_code == HTTPStatus.BAD_REQUEST
    assert r.get_json()["code"] == "NOT_A_GIT_REPO"
    assert r.get_json()["error"] == _MESSAGE


def test_a_trailing_dot_segment_is_refused_and_starts_no_job(client, created, tmp_path):
    specs, _invalidate = created
    origin = _bare(tmp_path)
    for suffix in ("/.", "/..", "/sub/.."):
        r = client.post("/api/projects", json={"repo": f"file://{origin}{suffix}"}, headers=_ORIGIN)
        assert r.status_code == HTTPStatus.BAD_REQUEST
    assert specs == []
    assert client.get("/api/projects/clone-status").get_json()["state"] == "idle"
