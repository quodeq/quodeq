"""Machine-readable error-code coverage for POST /api/projects's duplicate
branch: tools/check_error_codes.py's zero-tolerance gate found one bare
jsonify() under routes_project_create.py. PROJECT_EXISTS is the spelling
import_project.py already uses for the same "project already exists"
condition.

The ``client`` fixture is reused, not copied, from test_routes_project_create.py.
"""
from __future__ import annotations

from unittest.mock import patch

from quodeq.services.base import CreateProjectResult
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


def test_post_projects_non_string_discipline_returns_400(client):
    # ephemeral: True avoids the unrelated "cloneDest is required" branch, so
    # this isolates the discipline-specific type check.
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
