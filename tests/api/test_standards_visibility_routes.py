"""Tests for GET/PUT /api/projects/<project_id>/standards-visibility."""
import json
from pathlib import Path

import pytest

from quodeq.api.app import create_app
from quodeq.core.standards.visibility import DEFAULT_VISIBLE_STANDARDS, VISIBILITY_RELPATH

# PUT is a state-changing request; the CSRF check in quodeq.api.security
# requires a same-origin Origin header on it (see
# tests/api/test_standards_overrides_routes.py's identical _LOCALHOST use).
_LOCALHOST = {"Origin": "http://localhost"}


@pytest.fixture()
def project_id() -> str:
    return "proj-1"


@pytest.fixture()
def detached_project_id() -> str:
    """A project id with no local working copy, driving the 404 branch."""
    return "proj-detached"


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture()
def client(repo_root: Path, project_id: str, monkeypatch: pytest.MonkeyPatch):
    """A test client with no STANDARDS_* overrides, so knownStandardIds comes
    from the real bundled compiled standards (security, clean-architecture,
    etc.) -- unlike test_standards_overrides_routes.py's client, which stubs
    a tiny compiled dir because it only cares about override validation
    against specific params, not the full known-id catalog.
    """
    app = create_app(test_config={"TESTING": True})

    import quodeq.api.standards_visibility_routes as _mod
    monkeypatch.setattr(
        _mod, "resolve_repo_root",
        lambda pid: str(repo_root) if pid == project_id else None,
    )

    with app.test_client() as c:
        yield c


def test_get_returns_defaults_when_no_file(client, project_id):
    resp = client.get(f"/api/projects/{project_id}/standards-visibility")
    assert resp.status_code == 200
    assert resp.get_json()["visibleStandardIds"] == list(DEFAULT_VISIBLE_STANDARDS)
    assert resp.get_json()["isDefault"] is True


def test_get_reports_default_standard_ids(client, project_id):
    """Additive `defaultStandardIds` lets the UI reconcile its boot-time
    fallback against the server's own default set instead of duplicating
    it as a second source of truth."""
    body = client.get(f"/api/projects/{project_id}/standards-visibility").get_json()
    assert body["defaultStandardIds"] == list(DEFAULT_VISIBLE_STANDARDS)


def test_get_reports_known_standard_ids(client, project_id):
    body = client.get(f"/api/projects/{project_id}/standards-visibility").get_json()
    assert "security" in body["knownStandardIds"]
    assert "clean-architecture" in body["knownStandardIds"]


def test_put_persists_and_get_reads_back(client, project_id, repo_root):
    resp = client.put(f"/api/projects/{project_id}/standards-visibility",
                       json={"visibleStandardIds": ["security", "clean-architecture"]},
                       headers=_LOCALHOST)
    assert resp.status_code == 200
    assert resp.get_json()["isDefault"] is False
    saved = json.loads((repo_root / VISIBILITY_RELPATH).read_text(encoding="utf-8"))
    assert saved == {"version": 1,
                     "visibleStandardIds": ["security", "clean-architecture"]}
    again = client.get(f"/api/projects/{project_id}/standards-visibility").get_json()
    assert again["visibleStandardIds"] == ["security", "clean-architecture"]


def test_put_rejects_unknown_standard(client, project_id, repo_root):
    resp = client.put(f"/api/projects/{project_id}/standards-visibility",
                       json={"visibleStandardIds": ["not-a-standard"]},
                       headers=_LOCALHOST)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_visibility"
    assert not (repo_root / VISIBILITY_RELPATH).exists()


def test_put_rejects_missing_key(client, project_id):
    resp = client.put(f"/api/projects/{project_id}/standards-visibility", json={},
                       headers=_LOCALHOST)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "bad_request"


def test_put_accepts_empty_selection(client, project_id, repo_root):
    resp = client.put(f"/api/projects/{project_id}/standards-visibility",
                       json={"visibleStandardIds": []},
                       headers=_LOCALHOST)
    assert resp.status_code == 200
    assert resp.get_json()["visibleStandardIds"] == []
    assert (repo_root / VISIBILITY_RELPATH).is_file()


def test_routes_404_when_project_has_no_local_repo(client, detached_project_id):
    for call in (client.get, client.put):
        resp = call(f"/api/projects/{detached_project_id}/standards-visibility",
                    json={"visibleStandardIds": []}, headers=_LOCALHOST)
        assert resp.status_code == 404
