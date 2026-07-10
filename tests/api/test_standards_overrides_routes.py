"""Tests for GET/PUT /api/projects/<project_id>/standards-overrides."""
import json
from pathlib import Path

import pytest

from quodeq.api.app import create_app

OVERRIDES_URL = "/api/projects/proj-1/standards-overrides"


def _write_compiled_dim(compiled_dir: Path) -> None:
    (compiled_dir / "maintainability.json").write_text(json.dumps({
        "id": "maintainability",
        "principles": [{"name": "Analyzability", "requirements": [{
            "id": "M-ANA-2",
            "text": "Functions MUST NOT exceed {max_lines} lines",
            "params": {"max_lines": {"label": "Max function lines", "type": "int",
                                     "default": 50, "min": 10, "max": 500}},
        }]}],
    }))


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    return root


@pytest.fixture()
def client(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch):
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()
    _write_compiled_dim(compiled_dir)

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: str(project_root) if pid == "proj-1" else None)

    with app.test_client() as c:
        yield c


@pytest.fixture()
def client_without_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    compiled_dir = tmp_path / "compiled"
    compiled_dir.mkdir()

    dims = tmp_path / "dimensions.json"
    dims.write_text(json.dumps({"applies": []}))
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()

    app = create_app(test_config={
        "TESTING": True,
        "STANDARDS_EVALUATORS_DIR": str(evaluators),
        "STANDARDS_COMPILED_DIR": str(compiled_dir),
        "STANDARDS_DIMENSIONS_FILE": str(dims),
    })

    import quodeq.api.standards_overrides_routes as _mod
    monkeypatch.setattr(_mod, "resolve_repo_root", lambda pid: None)

    with app.test_client() as c:
        yield c


def test_get_returns_empty_when_no_file(client):
    resp = client.get(OVERRIDES_URL)
    assert resp.status_code == 200
    assert resp.get_json() == {"overrides": {}, "counts": {}}


_LOCALHOST = {"Origin": "http://localhost"}


def test_put_then_get_roundtrip(client, project_root: Path):
    resp = client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 60}}},
                      headers=_LOCALHOST)
    assert resp.status_code == 200
    saved = json.loads((project_root / ".quodeq" / "standards-overrides.json").read_text())
    assert saved == {"version": 1, "overrides": {"M-ANA-2": {"max_lines": 60}}}
    resp = client.get(OVERRIDES_URL)
    assert resp.get_json() == {
        "overrides": {"M-ANA-2": {"max_lines": 60}},
        "counts": {"maintainability": 1},
    }


def test_put_rejects_out_of_bounds(client, project_root: Path):
    resp = client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 99999}}},
                      headers=_LOCALHOST)
    assert resp.status_code == 400
    body = resp.get_json()
    assert "details" in body
    assert any("M-ANA-2.max_lines" in d for d in body["details"])
    assert not (project_root / ".quodeq" / "standards-overrides.json").exists()


def test_put_empty_deletes_file(client, project_root: Path):
    client.put(OVERRIDES_URL, json={"overrides": {"M-ANA-2": {"max_lines": 60}}},
               headers=_LOCALHOST)
    resp = client.put(OVERRIDES_URL, json={"overrides": {}}, headers=_LOCALHOST)
    assert resp.status_code == 200
    assert not (project_root / ".quodeq" / "standards-overrides.json").exists()


def test_unknown_project_is_404(client_without_repo_root):
    resp = client_without_repo_root.get(OVERRIDES_URL)
    assert resp.status_code == 404
