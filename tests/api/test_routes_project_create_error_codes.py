"""Machine-readable error-code coverage for POST /api/projects's duplicate
branch: tools/check_error_codes.py's zero-tolerance gate found one bare
jsonify() under routes_project_create.py. PROJECT_EXISTS is the spelling
services/project_import.py already uses for the same "project already exists"
condition.

The ``client`` fixture is reused, not copied, from test_routes_project_create.py.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from quodeq.services.base import CreateProjectResult, CreateProjectStatus
from quodeq.shared.git_errors import GitFailureKind
from tests.api.test_routes_project_create import _ORIGIN, client  # noqa: F401 -- client is a pytest fixture


def test_post_projects_duplicate_has_code(client):
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=CreateProjectResult(status="duplicate", existing_project_id="abc123"),
    ):
        resp = client.post(
            "/api/projects",
            json={"repo": "https://github.com/x/y.git", "ephemeral": True},
            headers=_ORIGIN,
        )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "PROJECT_EXISTS"
    assert body["existingProjectId"] == "abc123"


def test_post_projects_non_object_body_has_code(client):  # 2686
    resp = client.post("/api/projects", json=[1], headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["code"] == "INVALID_INPUT"


def _created_result():
    return CreateProjectResult(status="created", project_id="x", scan_data={})


def test_post_projects_non_string_repo_returns_400(client):
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post("/api/projects", json={"repo": 5}, headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["code"]
    mock_create.assert_not_called()


def test_post_projects_non_string_clone_dest_returns_400(client):
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post(
            "/api/projects",
            json={"repo": "https://x/y.git", "cloneDest": ["a"]},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["code"]
    mock_create.assert_not_called()


def test_post_projects_string_ephemeral_returns_400(client):
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post(
            "/api/projects",
            json={"repo": "https://x/y.git", "ephemeral": "false"},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400
    assert resp.is_json
    body = resp.get_json()
    assert body["code"] == "INVALID_PARAM"
    assert "ephemeral" in body["error"]
    mock_create.assert_not_called()


def test_post_projects_real_bool_ephemeral_true_is_unaffected(client):
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post(
            "/api/projects",
            json={"repo": "https://x/y.git", "ephemeral": True},
            headers=_ORIGIN,
        )
    assert resp.status_code == 200
    mock_create.assert_called_once()


def test_post_projects_real_bool_ephemeral_false_is_unaffected(client, tmp_path, inline_clone_job):
    # cloneDest must be an existing dir under home; the shared `client`
    # fixture patches Path.home to tmp_path.
    clone_dest = tmp_path / "code"
    clone_dest.mkdir()
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post(
            "/api/projects",
            json={"repo": "https://x/y.git", "ephemeral": False, "cloneDest": str(clone_dest)},
            headers=_ORIGIN,
        )
    assert resp.status_code == 202
    mock_create.assert_called_once()


def test_post_projects_null_ephemeral_is_treated_as_absent(client, tmp_path, inline_clone_job):
    clone_dest = tmp_path / "code"
    clone_dest.mkdir()
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post(
            "/api/projects",
            json={"repo": "https://x/y.git", "ephemeral": None, "cloneDest": str(clone_dest)},
            headers=_ORIGIN,
        )
    assert resp.status_code == 202
    mock_create.assert_called_once()


def test_post_projects_non_string_discipline_returns_400(client):
    # ephemeral: True keeps the request synchronous, so this isolates the
    # discipline-specific type check from the clone job.
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project",
        return_value=_created_result(),
    ) as mock_create:
        resp = client.post(
            "/api/projects",
            json={"repo": "https://x/y.git", "ephemeral": True, "discipline": 3},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400
    assert resp.is_json
    assert resp.get_json()["code"]
    mock_create.assert_not_called()


@pytest.mark.parametrize(
    "kind,code,status",
    [
        (GitFailureKind.HOST_KEY, "HOST_KEY_UNVERIFIED", 400),
        (GitFailureKind.TIMEOUT, "CLONE_TIMEOUT", 504),
        (GitFailureKind.GIT_MISSING, "GIT_MISSING", 500),
        (GitFailureKind.UNKNOWN, "CLONE_UNKNOWN", 502),
    ],
)
def test_clone_failure_codes_and_detail(client, kind, code, status):
    result = CreateProjectResult(
        status=CreateProjectStatus.CLONE_FAILED, message="git clone failed",
        clone_error_kind=kind, clone_stderr="fatal: the real reason\n",
    )
    with patch(
        "quodeq.services.filesystem.FilesystemActionProvider.create_project", return_value=result,
    ):
        resp = client.post(
            "/api/projects", json={"repo": "https://github.com/o/r.git", "ephemeral": True}, headers=_ORIGIN,
        )
    assert resp.status_code == status
    body = resp.get_json()
    assert body["code"] == code
    assert body["detail"] == "fatal: the real reason"
