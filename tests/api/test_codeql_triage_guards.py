"""Guards added in the CodeQL alert triage.

Covers the two real path-injection gaps the triage found:
- ``POST /api/evaluations`` must apply the same scan allowlist as
  ``/api/scan`` and ``POST /api/projects`` (its ``repo`` body field used to
  accept any readable directory and persist its file tree).
- ``scopePath`` must be a plain relative subpath at both entry routes, and
  the manifest walk must not follow a persisted scope outside the repo.

Plus the consistency hardenings: route-level project-id validation on
info/delete/path and the standards-visibility pair.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from quodeq.api.app import create_app
from quodeq.shared.validation import validate_relative_scope

_ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    evaluations_dir = tmp_path / "evaluations"
    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(evaluations_dir))
    app = create_app(test_config={"TESTING": True})
    with app.test_client() as c:
        yield c, tmp_path.resolve()


def _patch_home(home: Path):
    return patch("pathlib.Path.home", new=classmethod(lambda cls: home))


# ---------------------------------------------------------------------------
# POST /api/evaluations repo allowlist (G1)
# ---------------------------------------------------------------------------

def test_start_evaluation_rejects_repo_outside_home(app_client):
    c, home = app_client
    with _patch_home(home):
        resp = c.post("/api/evaluations", json={"repo": "/usr/share"}, headers=_ORIGIN)
    assert resp.status_code == 403, resp.get_json()
    assert resp.get_json()["code"] == "FORBIDDEN"


def test_start_evaluation_rejects_blocked_system_dir(app_client):
    c, home = app_client
    with _patch_home(home):
        resp = c.post("/api/evaluations", json={"repo": "/etc"}, headers=_ORIGIN)
    assert resp.status_code == 403, resp.get_json()


def test_start_evaluation_rejects_traversal_scope_path(app_client):
    c, home = app_client
    repo = home / "myrepo"
    repo.mkdir()
    with _patch_home(home):
        resp = c.post(
            "/api/evaluations",
            json={"repo": str(repo), "scopePath": "../../etc"},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400, resp.get_json()
    assert "scope" in (resp.get_json().get("error") or "").lower()


# ---------------------------------------------------------------------------
# POST /api/projects scopePath validation (G2, entry side)
# ---------------------------------------------------------------------------

def test_create_project_rejects_traversal_scope_path(app_client):
    c, home = app_client
    repo = home / "myrepo"
    repo.mkdir()
    (repo / ".git").mkdir()
    with _patch_home(home):
        resp = c.post(
            "/api/projects",
            json={"repo": str(repo), "scopePath": "../outside"},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["code"] == "INVALID_SCOPE"


def test_create_project_rejects_absolute_scope_path(app_client):
    c, home = app_client
    repo = home / "myrepo"
    repo.mkdir()
    (repo / ".git").mkdir()
    with _patch_home(home):
        resp = c.post(
            "/api/projects",
            json={"repo": str(repo), "scopePath": "/etc"},
            headers=_ORIGIN,
        )
    assert resp.status_code == 400, resp.get_json()
    assert resp.get_json()["code"] == "INVALID_SCOPE"


# ---------------------------------------------------------------------------
# validate_relative_scope unit behavior
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["../x", "a/../../b", "/abs", "C:evil", "a\\b", "a\0b"])
def test_validate_relative_scope_rejects(bad):
    with pytest.raises(ValueError):
        validate_relative_scope(bad)


@pytest.mark.parametrize("ok", ["src", "src/backend", "a.b/c-d_e", "src/with..dots"])
def test_validate_relative_scope_accepts(ok):
    validate_relative_scope(ok)  # must not raise


# ---------------------------------------------------------------------------
# Manifest walk containment (G2, sink side)
# ---------------------------------------------------------------------------

def test_walk_and_group_ignores_escaping_scope(tmp_path):
    from quodeq.analysis.manifest_build import _walk_and_group

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("x = 1\n")
    src = tmp_path / "repo"
    src.mkdir()
    (src / "main.py").write_text("y = 2\n")

    files_by_lang, _, _ = _walk_and_group(
        src, {".py": "python"}, set(), [], scope_path="../outside",
    )
    all_files = [f for files in files_by_lang.values() for f in files]
    assert not any("secret" in f for f in all_files)
    assert any("main.py" in f for f in all_files)


def test_walk_and_group_ignores_symlink_scope_escape(tmp_path):
    from quodeq.analysis.manifest_build import _walk_and_group

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("x = 1\n")
    src = tmp_path / "repo"
    src.mkdir()
    (src / "main.py").write_text("y = 2\n")
    (src / "link").symlink_to(outside)

    files_by_lang, _, _ = _walk_and_group(
        src, {".py": "python"}, set(), [], scope_path="link",
    )
    all_files = [f for files in files_by_lang.values() for f in files]
    assert not any("secret" in f for f in all_files)


def test_walk_and_group_valid_scope_still_narrows(tmp_path):
    from quodeq.analysis.manifest_build import _walk_and_group

    src = tmp_path / "repo"
    (src / "sub").mkdir(parents=True)
    (src / "root.py").write_text("a = 1\n")
    (src / "sub" / "inner.py").write_text("b = 2\n")

    files_by_lang, _, _ = _walk_and_group(
        src, {".py": "python"}, set(), [], scope_path="sub",
    )
    all_files = [f for files in files_by_lang.values() for f in files]
    assert any("inner.py" in f for f in all_files)
    assert not any("root.py" in f for f in all_files)


# ---------------------------------------------------------------------------
# Route-level project-id validation consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/api/projects/{pid}/info"),
    ("delete", "/api/projects/{pid}"),
    ("patch", "/api/projects/{pid}/path"),
    ("get", "/api/projects/{pid}/standards-visibility"),
    ("put", "/api/projects/{pid}/standards-visibility"),
])
def test_traversal_project_id_rejected(app_client, method, path):
    c, home = app_client
    url = path.format(pid="..%5Cetc")  # backslash traversal survives URL routing
    with _patch_home(home):
        resp = getattr(c, method)(url, headers=_ORIGIN, json={})
    assert resp.status_code == 400, (method, path, resp.status_code)
