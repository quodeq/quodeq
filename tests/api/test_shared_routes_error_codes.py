"""Error-code coverage for the shared-repository route modules.

Task 2 of usability cycle 1 (findings 6104, 6105, 6106, 6111, 6001, 6002,
6003, 6004): every error response under ``routes_shared_common.py`` and
``routes_shared_config.py`` now carries a machine-readable ``code``, and the
FOREIGN_REPO message names the fix (finding 6111). Shared fixtures come from
``tests/api/_routes_shared_fixtures.py``; the state-setup helpers mirror
``tests/api/test_routes_shared_read.py``/``test_routes_shared_config.py``
rather than duplicating their fixtures.
"""
from __future__ import annotations

import json

from quodeq.data.fs.shared_repo import FORMAT_NAME, MARKER_FILENAME, shared_repo_path
from quodeq.services.shared_connect import ConnectOutcome
from quodeq.services.shared_settings import SharedSettings, write_settings
from tests.api._routes_shared_fixtures import (  # noqa: F401 -- client/_clean_publish_status are pytest fixtures
    _ORIGIN,
    _clean_publish_status,
    client,
)

# --- _with_shared_root (routes_shared_common.py) -----------------------------


def test_shared_root_unconfigured_has_no_shared_repo_code(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "NO_SHARED_REPO"


def test_shared_root_unsupported_version_has_code(client):
    url = "file:///dummy/unsupported.git"
    repo = shared_repo_path(url)
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / MARKER_FILENAME).write_text(
        json.dumps({"format": FORMAT_NAME, "version": 99}), encoding="utf-8",
    )
    write_settings(SharedSettings(url=url))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "UNSUPPORTED_VERSION"


def test_shared_root_missing_has_shared_repo_missing_code(client):
    write_settings(SharedSettings(url="file:///nonexistent/repo.git"))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 503
    assert resp.get_json()["code"] == "SHARED_REPO_MISSING"


def test_shared_root_foreign_message_tells_user_to_reconnect(client):
    """Finding 6111: the FOREIGN_REPO message must give a next step, mirroring
    the "missing" branch's "reconnect it in Settings" wording."""
    url = "file:///dummy/foreign.git"
    repo = shared_repo_path(url)
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    (repo / "README.md").write_text("some other project", encoding="utf-8")
    write_settings(SharedSettings(url=url))
    resp = client.get("/api/shared/projects")
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["code"] == "FOREIGN_REPO"
    assert "reconnect it in Settings" in body["error"]
    assert body["error"].startswith(
        "the configured repository does not look like a quodeq results repository"
    )


# --- routes_shared_config.py --------------------------------------------------


def test_put_config_invalid_url_has_code(client, monkeypatch):
    monkeypatch.setattr(
        "quodeq.api.routes_shared_config.connect_shared_repo",
        lambda url, **_kwargs: ConnectOutcome(status="invalid_url", url=url, detail="bad url"),
    )
    resp = client.put("/api/shared/config", json={"url": "not-a-url"}, headers=_ORIGIN)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["code"] == "INVALID_URL"
    assert body["error"] == "bad url"


def test_shared_refresh_no_repo_configured_has_code(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.post("/api/shared/refresh", headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "NO_SHARED_REPO"


def test_publish_start_invalid_project_segment_has_code(client):
    resp = client.post("/api/projects/../publish", headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "INVALID_INPUT"


def test_publish_start_no_repo_configured_has_code(client, monkeypatch, tmp_path):
    monkeypatch.setenv("QUODEQ_DIR", str(tmp_path))
    resp = client.post("/api/projects/some-project/publish", headers=_ORIGIN)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "NO_SHARED_REPO"
